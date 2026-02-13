import json
import re
from collections.abc import AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any

from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI
from app.config import settings

client = wrap_openai(
    AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
)

# Type alias for the retrieval callback
RetrieveFn = Callable[..., Awaitable[list[dict]]]

SYSTEM_PROMPT = "You are a helpful assistant."

SYSTEM_PROMPT_WITH_TOOLS = (
    "You are a helpful assistant with access to tools.\n\n"
    "Available capabilities:\n"
    "1. **retrieve_documents** — Search the user's uploaded documents for relevant content. "
    "Use this when the user asks about information that might be in their documents.\n"
    "2. **query_documents_metadata** — Query structured metadata about the user's documents "
    "(counts, file types, topics, dates, etc.). Use this for questions like 'how many documents do I have?', "
    "'what topics are covered?', 'list my PDF files'.\n"
    "3. **web_search** — Search the web for current information. Use this when the user asks about "
    "topics not likely in their documents, or asks for up-to-date information, news, or general knowledge.\n"
    "4. **deep_analysis** — Perform thorough, multi-pass analysis of the user's documents. "
    "Use this when asked for comprehensive analysis, detailed summaries, or deep investigation "
    "across documents. Prefer this over retrieve_documents when thoroughness is important.\n"
    "5. **graph_search** — Query the knowledge graph built from the user's documents. "
    "Use mode='global' for questions about main themes, topics, or a high-level overview of all documents. "
    "Use mode='relationship' with entity_a and entity_b to explain how two specific entities are connected.\n\n"
    "Choose the most appropriate tool for each query. You may use multiple tools if needed. "
    "When citing information from documents, mention it came from their uploaded documents. "
    "When citing web results, mention the source."
)

# --- Tool Definitions ---

RETRIEVE_TOOL = {
    "type": "function",
    "function": {
        "name": "retrieve_documents",
        "description": "Search the user's uploaded documents for information relevant to their query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant document chunks.",
                },
                "date_from": {
                    "type": "string",
                    "description": "Optional start date filter (YYYY-MM-DD).",
                },
                "date_to": {
                    "type": "string",
                    "description": "Optional end date filter (YYYY-MM-DD).",
                },
                "recency_weight": {
                    "type": "number",
                    "description": "Weight 0-1 for recency bias. 0 = pure similarity.",
                },
            },
            "required": ["query"],
        },
    },
}

SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "query_documents_metadata",
        "description": (
            "Query structured metadata about the user's documents using natural language. "
            "Use for questions about document counts, file types, topics, dates, sizes, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The natural language question about document metadata.",
                },
            },
            "required": ["question"],
        },
    },
}

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information, news, or general knowledge. "
            "Use when the answer is unlikely to be in the user's documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    },
}

DEEP_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "deep_analysis",
        "description": (
            "Perform a thorough, multi-pass analysis of the user's documents. "
            "Use when the user asks for comprehensive analysis, detailed summaries, "
            "or deep investigation across their documents. This does multiple rounds "
            "of retrieval with different queries to ensure thorough coverage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The analysis query describing what to investigate.",
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific areas or topics to focus on.",
                },
            },
            "required": ["query"],
        },
    },
}


GRAPH_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "graph_search",
        "description": (
            "Query the knowledge graph extracted from the user's documents. "
            "Use mode='global' for high-level themes, main topics, or an overview of all documents. "
            "Use mode='relationship' with entity_a and entity_b to find how two entities are connected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["global", "relationship"],
                    "description": "'global' for theme/community overview; 'relationship' for entity path queries.",
                },
                "entity_a": {
                    "type": "string",
                    "description": "First entity name (required for mode='relationship').",
                },
                "entity_b": {
                    "type": "string",
                    "description": "Second entity name (required for mode='relationship').",
                },
            },
            "required": ["mode"],
        },
    },
}


def get_tools(has_documents: bool) -> list[dict]:
    tools = []
    if has_documents:
        tools.append(RETRIEVE_TOOL)
    if settings.sql_tool_enabled and has_documents:
        tools.append(SQL_TOOL)
    if settings.web_search_enabled and settings.perplexity_api_key:
        tools.append(WEB_SEARCH_TOOL)
    if settings.sub_agents_enabled and has_documents:
        tools.append(DEEP_ANALYSIS_TOOL)
    if settings.graphrag_enabled and has_documents:
        tools.append(GRAPH_SEARCH_TOOL)
    return tools


# --- ToolContext ---

@dataclass
class ToolContext:
    retrieve_fn: RetrieveFn | None = None
    user_token: str = ""
    user_id: str = ""
    has_documents: bool = False


# --- ToolEvent (non-token events yielded from stream) ---

@dataclass
class ToolEvent:
    tool_name: str
    data: Any


# --- Helpers ---

def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant documents found."
    parts = []
    for i, c in enumerate(chunks, 1):
        header = f"[Chunk {i}]"
        if c.get("doc_title"):
            header += f" (from: {c['doc_title']})"
        if c.get("doc_date"):
            header += f" [date: {c['doc_date']}]"
        if c.get("doc_topics"):
            header += f" [topics: {', '.join(c['doc_topics'])}]"
        score = c.get("rerank_score") or c.get("rrf_score") or c.get("similarity", 0)
        header += f" (score: {score:.2f})"
        if c.get("graph_expanded"):
            header += " [graph-expanded]"
        parts.append(f"{header}\n{c['content']}")
    return "\n\n".join(parts)


def _parse_text_tool_calls(content: str) -> list[dict] | None:
    """Parse tool calls formatted as text by local LLMs.

    Detects patterns like:
        <function=web_search>
        <parameter=query>some query</parameter>
        </function>
    """
    pattern = r"<function=(\w+)>(.*?)</function>"
    matches = re.findall(pattern, content, re.DOTALL)
    if not matches:
        return None

    tool_calls = []
    for func_name, body in matches:
        params = {}
        param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
        param_matches = re.findall(param_pattern, body, re.DOTALL)
        for param_name, param_value in param_matches:
            params[param_name] = param_value.strip()
        tool_calls.append({"name": func_name, "arguments": params})

    return tool_calls if tool_calls else None


async def _execute_tool(
    tool_name: str,
    args: dict,
    ctx: ToolContext,
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> str | dict:
    if tool_name == "retrieve_documents" and ctx.retrieve_fn:
        query = args.get("query", "")
        kwargs = {}
        if "date_from" in args:
            kwargs["date_from"] = args["date_from"]
        if "date_to" in args:
            kwargs["date_to"] = args["date_to"]
        if "recency_weight" in args:
            kwargs["recency_weight"] = float(args["recency_weight"])
        chunks = await ctx.retrieve_fn(query, **kwargs)
        return _format_chunks(chunks)

    elif tool_name == "query_documents_metadata":
        from app.services.sql_tool import execute_metadata_query
        question = args.get("question", "")
        return await execute_metadata_query(question, ctx.user_token)

    elif tool_name == "web_search":
        from app.services.web_search import search_web
        query = args.get("query", "")
        return await search_web(query)

    elif tool_name == "deep_analysis" and ctx.retrieve_fn:
        from app.services.sub_agent import run_sub_agent
        query = args.get("query", "")
        focus_areas = args.get("focus_areas")
        return await run_sub_agent(
            query=query,
            retrieve_fn=ctx.retrieve_fn,
            user_token=ctx.user_token,
            focus_areas=focus_areas,
            on_status=on_status,
        )

    elif tool_name == "graph_search":
        from app.services.graph_retrieval import global_graph_search, relationship_graph_search
        mode = args.get("mode", "global")
        if mode == "relationship":
            entity_a = args.get("entity_a", "")
            entity_b = args.get("entity_b", "")
            if not entity_a or not entity_b:
                return "relationship mode requires both entity_a and entity_b."
            return await relationship_graph_search(
                entity_a, entity_b, ctx.user_token, user_id=ctx.user_id
            )
        else:
            return await global_graph_search(
                ctx.user_token, settings.graphrag_global_communities_top_n, user_id=ctx.user_id
            )

    return f"Unknown tool: {tool_name}"


# --- Main streaming function ---

MAX_TOOL_ROUNDS = 3


@traceable(name="chat_completion", run_type="llm")
async def stream_chat_completion(
    messages: list[dict],
    thread_id: str = "",
    user_id: str = "",
    tool_ctx: ToolContext | None = None,
) -> AsyncIterator[str | ToolEvent]:
    tools = get_tools(tool_ctx.has_documents) if tool_ctx else []
    system_prompt = SYSTEM_PROMPT_WITH_TOOLS if tools else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    metadata = {
        "thread_id": thread_id,
        "user_id": user_id,
        "message_count": len(messages),
    }

    if not tools:
        # No tools — stream directly
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,
            stream=True,
            langsmith_extra={"metadata": metadata},
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        return

    # Status collector for sub-agent
    status_events: list[ToolEvent] = []
    used_deep_analysis = False

    async def on_status(phase: str):
        status_events.append(ToolEvent(tool_name="deep_analysis", data={"phase": phase}))

    # Multi-round tool loop
    for round_num in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,
            tools=tools,
            langsmith_extra={"metadata": {**metadata, "phase": f"tool_check_{round_num}"}},
        )
        choice = response.choices[0]

        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            # Check for text-formatted tool calls from local LLMs
            text_tool_calls = _parse_text_tool_calls(choice.message.content or "")
            if text_tool_calls:
                # Inject as assistant message so conversation stays coherent
                full_messages.append({"role": "assistant", "content": choice.message.content})
                for tc in text_tool_calls:
                    if tc["name"] == "deep_analysis":
                        used_deep_analysis = True
                    status_events.clear()
                    result = await _execute_tool(tc["name"], tc["arguments"], tool_ctx, on_status)
                    for evt in status_events:
                        yield evt
                    status_events.clear()
                    if tc["name"] == "web_search" and isinstance(result, dict):
                        yield ToolEvent(tool_name="web_search", data=result)
                        tool_result_str = result.get("answer", "")
                    elif isinstance(result, dict):
                        tool_result_str = json.dumps(result, default=str)
                    else:
                        tool_result_str = result
                    full_messages.append({"role": "user", "content": f"[Tool result for {tc['name']}]: {tool_result_str}"})
                # Continue loop to get final answer from LLM
                continue

            # No tool call — yield content and done
            if used_deep_analysis:
                yield ToolEvent(tool_name="deep_analysis", data={"done": True})
            if choice.message.content:
                yield choice.message.content
            return

        # Process all tool calls in this response
        full_messages.append(choice.message.model_dump())

        for tool_call in choice.message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if name == "deep_analysis":
                used_deep_analysis = True
            status_events.clear()
            result = await _execute_tool(name, args, tool_ctx, on_status)
            for evt in status_events:
                yield evt
            status_events.clear()

            # For web_search, yield a ToolEvent with structured results, then use answer text as tool result
            if name == "web_search" and isinstance(result, dict):
                yield ToolEvent(tool_name="web_search", data=result)
                tool_result_str = result.get("answer", "")
            elif isinstance(result, dict):
                tool_result_str = json.dumps(result, default=str)
            else:
                tool_result_str = result

            full_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_str,
                }
            )

    # Signal deep analysis completion before final streaming
    if used_deep_analysis:
        yield ToolEvent(tool_name="deep_analysis", data={"done": True})

    # After all tool rounds, stream the final response
    final_response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=full_messages,
        stream=True,
        langsmith_extra={"metadata": {**metadata, "phase": "final_response"}},
    )
    async for chunk in final_response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
