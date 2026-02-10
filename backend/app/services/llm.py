import json
from collections.abc import AsyncIterator, Callable, Awaitable

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

SYSTEM_PROMPT = "You are a helpful assistant."

SYSTEM_PROMPT_WITH_RETRIEVAL = (
    "You are a helpful assistant with access to the user's uploaded documents. "
    "When the user asks a question that might be answered by their documents, "
    "use the retrieve_documents tool to search for relevant information. "
    "When citing information from documents, mention that it came from their uploaded documents."
)

TOOLS = [
    {
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
                        "description": "Optional start date filter (YYYY-MM-DD). Only return documents from this date onward.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Optional end date filter (YYYY-MM-DD). Only return documents up to this date.",
                    },
                    "recency_weight": {
                        "type": "number",
                        "description": "Weight between 0 and 1 for recency bias. 0 = pure similarity, higher values favor newer documents.",
                    },
                },
                "required": ["query"],
            },
        },
    }
]

# Type alias for the retrieval callback
RetrieveFn = Callable[..., Awaitable[list[dict]]]


@traceable(name="chat_completion", run_type="llm")
async def stream_chat_completion(
    messages: list[dict],
    thread_id: str = "",
    user_id: str = "",
    retrieve_fn: RetrieveFn | None = None,
) -> AsyncIterator[str]:
    system_prompt = SYSTEM_PROMPT_WITH_RETRIEVAL if retrieve_fn else SYSTEM_PROMPT
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    metadata = {
        "thread_id": thread_id,
        "user_id": user_id,
        "message_count": len(messages),
    }

    if retrieve_fn is None:
        # No documents — stream directly, no tools
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

    # Has documents — non-streaming first call with tools
    first_response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=full_messages,
        tools=TOOLS,
        langsmith_extra={"metadata": {**metadata, "phase": "tool_check"}},
    )
    choice = first_response.choices[0]

    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        # LLM wants to call retrieve_documents
        tool_call = choice.message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        query = args.get("query", messages[-1]["content"] if messages else "")

        # Extract optional retrieval params
        retrieve_kwargs = {}
        if "date_from" in args:
            retrieve_kwargs["date_from"] = args["date_from"]
        if "date_to" in args:
            retrieve_kwargs["date_to"] = args["date_to"]
        if "recency_weight" in args:
            retrieve_kwargs["recency_weight"] = float(args["recency_weight"])

        # Execute retrieval
        chunks = await retrieve_fn(query, **retrieve_kwargs)

        # Build tool result with metadata
        if chunks:
            context_parts = []
            for i, c in enumerate(chunks, 1):
                header = f"[Chunk {i}]"
                if c.get("doc_title"):
                    header += f" (from: {c['doc_title']})"
                if c.get("doc_date"):
                    header += f" [date: {c['doc_date']}]"
                if c.get("doc_topics"):
                    header += f" [topics: {', '.join(c['doc_topics'])}]"
                header += f" (score: {c.get('similarity', 0):.2f})"
                context_parts.append(f"{header}\n{c['content']}")
            tool_result = "\n\n".join(context_parts)
        else:
            tool_result = "No relevant documents found."

        # Append assistant message with tool call + tool result
        full_messages.append(choice.message.model_dump())
        full_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

        # Streaming second call with context
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,
            stream=True,
            langsmith_extra={"metadata": {**metadata, "phase": "final_response"}},
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    else:
        # No tool call — yield content from non-streaming response
        if choice.message.content:
            yield choice.message.content
