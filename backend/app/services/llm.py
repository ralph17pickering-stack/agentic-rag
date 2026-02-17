import json
import re
from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any

from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI
from app.config import settings
from app.tools._registry import ToolContext, ToolEvent
from app.tools._registry import (
    get_tools as _registry_get_tools,
    execute_tool as _registry_execute_tool,
)

client = wrap_openai(
    AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
    )
)


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> CoT blocks produced by reasoning models (e.g. Qwen3-Thinking)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

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

def get_tools(has_documents: bool) -> list[dict]:
    return _registry_get_tools(ToolContext(has_documents=has_documents))


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
    """Parse tool calls emitted as text by local LLMs.

    Handles three formats:
      1. <function=name><parameter=k>v</parameter></function>
      2. <tool_call>{"name": "...", "arguments": {...}}</tool_call>
      3. Bare JSON array: [{"name": "...", "arguments": {...}}]
    """
    if not content:
        return None

    # --- Format 1: <function=...> ---
    f1_matches = re.findall(r"<function=(\w+)>(.*?)</function>", content, re.DOTALL)
    if f1_matches:
        tool_calls = []
        for func_name, body in f1_matches:
            params = {}
            for param_name, param_value in re.findall(r"<parameter=(\w+)>(.*?)</parameter>", body, re.DOTALL):
                params[param_name] = param_value.strip()
            tool_calls.append({"name": func_name, "arguments": params})
        return tool_calls if tool_calls else None

    # --- Format 2: <tool_call>JSON</tool_call> ---
    f2_matches = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL)
    if f2_matches:
        tool_calls = []
        for raw_json in f2_matches:
            try:
                data = json.loads(raw_json)
                if isinstance(data, dict) and "name" in data:
                    tool_calls.append({
                        "name": data["name"],
                        "arguments": data.get("arguments", data.get("parameters", {})),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return tool_calls if tool_calls else None

    # --- Format 3: bare JSON array (strip optional code fence) ---
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-z]*\n?", "", stripped).rstrip("`").strip()
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
            if isinstance(data, list):
                tool_calls = [
                    {"name": item["name"], "arguments": item.get("arguments", {})}
                    for item in data
                    if isinstance(item, dict) and "name" in item
                ]
                return tool_calls if tool_calls else None
        except (json.JSONDecodeError, KeyError):
            pass

    return None


async def _execute_tool(
    tool_name: str,
    args: dict,
    ctx: ToolContext,
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> str | dict:
    return await _registry_execute_tool(tool_name, args, ctx, on_status=on_status)


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
            elif name == "retrieve_documents" and isinstance(result, dict):
                sources = result.get("citation_sources", [])
                yield ToolEvent(tool_name="retrieve_documents", data={"sources": sources})
                tool_result_str = result.get("formatted_text", "")
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
