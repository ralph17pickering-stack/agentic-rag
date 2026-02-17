import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langsmith import traceable

from app.config import settings
from app.services.llm import _format_chunks, client
from app.tools._registry import RetrieveFn

SUB_AGENT_SYSTEM_PROMPT = (
    "You are a thorough document analyst. Your job is to deeply analyze the user's "
    "documents to answer their query comprehensively.\n\n"
    "Strategy:\n"
    "1. Start with a broad retrieval to understand what's available\n"
    "2. Do follow-up retrievals with refined queries to fill gaps\n"
    "3. Use metadata queries to understand document structure if needed\n"
    "4. Synthesize all findings into a comprehensive answer\n\n"
    "You have these tools:\n"
    "- retrieve_documents(query) — search document content\n"
    "- query_documents_metadata(question) — query document metadata\n\n"
    "Do multiple rounds of retrieval with different queries to ensure thorough coverage. "
    "When you have enough information, provide your final synthesis."
)

SUB_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_documents",
            "description": "Search the user's uploaded documents for information relevant to the query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find relevant document chunks.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_documents_metadata",
            "description": "Query structured metadata about documents (counts, file types, topics, dates).",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about document metadata.",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

# Allowlist for sub-agent tool calls
_ALLOWED_TOOLS = {"retrieve_documents", "query_documents_metadata"}

STATUS_MESSAGES = [
    "Analyzing documents...",
    "Retrieving more context...",
    "Deepening analysis...",
    "Gathering additional details...",
    "Synthesizing findings...",
]


def _parse_sub_agent_tool_calls(content: str) -> list[dict] | None:
    """Parse text-formatted tool calls (local LLM compat), filtered to allowlist."""
    pattern = r"<function=(\w+)>(.*?)</function>"
    matches = re.findall(pattern, content, re.DOTALL)
    if not matches:
        return None

    tool_calls = []
    for func_name, body in matches:
        if func_name not in _ALLOWED_TOOLS:
            continue
        params = {}
        param_pattern = r"<parameter=(\w+)>(.*?)</parameter>"
        param_matches = re.findall(param_pattern, body, re.DOTALL)
        for param_name, param_value in param_matches:
            params[param_name] = param_value.strip()
        tool_calls.append({"name": func_name, "arguments": params})

    return tool_calls if tool_calls else None


async def _execute_sub_agent_tool(
    tool_name: str, args: dict, retrieve_fn: RetrieveFn, user_token: str
) -> str:
    if tool_name == "retrieve_documents":
        query = args.get("query", "")
        chunks = await retrieve_fn(query)
        return _format_chunks(chunks)

    if tool_name == "query_documents_metadata":
        from app.services.sql_tool import execute_metadata_query
        question = args.get("question", "")
        result = await execute_metadata_query(question, user_token)
        if isinstance(result, dict):
            return json.dumps(result, default=str)
        return result

    return f"Unknown tool: {tool_name}"


MAX_SUB_AGENT_ROUNDS = 5

OnStatusCallback = Callable[[str], Awaitable[None]]


@traceable(name="sub_agent_deep_analysis", run_type="chain")
async def run_sub_agent(
    query: str,
    retrieve_fn: RetrieveFn,
    user_token: str,
    focus_areas: list[str] | None = None,
    on_status: OnStatusCallback | None = None,
) -> str:
    """Run a multi-pass document analysis sub-agent."""
    user_msg = f"Analyze the following query thoroughly: {query}"
    if focus_areas:
        user_msg += f"\n\nFocus areas: {', '.join(focus_areas)}"

    messages = [
        {"role": "system", "content": SUB_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    if on_status:
        await on_status(STATUS_MESSAGES[0])

    for round_num in range(MAX_SUB_AGENT_ROUNDS):
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=SUB_AGENT_TOOLS,
        )
        choice = response.choices[0]

        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            # Check text-formatted tool calls
            text_tool_calls = _parse_sub_agent_tool_calls(choice.message.content or "")
            if text_tool_calls:
                messages.append({"role": "assistant", "content": choice.message.content})
                for tc in text_tool_calls:
                    result = await _execute_sub_agent_tool(
                        tc["name"], tc["arguments"], retrieve_fn, user_token
                    )
                    messages.append({
                        "role": "user",
                        "content": f"[Tool result for {tc['name']}]: {result}",
                    })
                if on_status:
                    status_idx = min(round_num + 1, len(STATUS_MESSAGES) - 1)
                    await on_status(STATUS_MESSAGES[status_idx])
                continue

            # No tool call — return final content
            return choice.message.content or ""

        # Process native tool calls
        messages.append(choice.message.model_dump())

        for tool_call in choice.message.tool_calls:
            name = tool_call.function.name
            if name not in _ALLOWED_TOOLS:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"Tool '{name}' is not available.",
                })
                continue

            args = json.loads(tool_call.function.arguments)
            result = await _execute_sub_agent_tool(name, args, retrieve_fn, user_token)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        if on_status:
            status_idx = min(round_num + 1, len(STATUS_MESSAGES) - 1)
            await on_status(STATUS_MESSAGES[status_idx])

    # After max rounds, ask for final synthesis
    messages.append({
        "role": "user",
        "content": "Please synthesize all the information you've gathered into a comprehensive final answer.",
    })
    final = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
    )
    return final.choices[0].message.content or ""
