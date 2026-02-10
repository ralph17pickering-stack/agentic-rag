from collections.abc import AsyncIterator

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


@traceable(name="chat_completion", run_type="llm")
async def stream_chat_completion(
    messages: list[dict],
    thread_id: str = "",
    user_id: str = "",
) -> AsyncIterator[str]:
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=full_messages,
        stream=True,
        langsmith_extra={
            "metadata": {
                "thread_id": thread_id,
                "user_id": user_id,
                "message_count": len(messages),
            }
        },
    )
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
