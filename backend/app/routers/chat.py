import json
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from app.dependencies import get_current_user
from app.services.supabase import get_supabase_client
from app.services.llm import stream_chat_completion, client
from app.services.retrieval import retrieve_chunks
from app.models.messages import MessageCreate, MessageResponse
from app.config import settings

router = APIRouter(prefix="/api/threads/{thread_id}", tags=["chat"])


@router.get("/messages", response_model=list[MessageResponse])
async def list_messages(thread_id: str, user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    result = (
        sb.table("messages")
        .select("*")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )
    return result.data


@router.post("/chat")
async def chat(
    thread_id: str, request: MessageCreate, user: dict = Depends(get_current_user)
):
    sb = get_supabase_client(user["token"])

    # Save user message
    sb.table("messages").insert(
        {
            "thread_id": thread_id,
            "user_id": user["id"],
            "role": "user",
            "content": request.content,
        }
    ).execute()

    # Fetch all messages for context
    result = (
        sb.table("messages")
        .select("*")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )
    messages_for_llm = [
        {"role": m["role"], "content": m["content"]} for m in result.data
    ]

    # Check if user has any ready documents — if so, enable retrieval
    retrieve_fn = None
    doc_check = (
        sb.table("documents")
        .select("id", count="exact")
        .eq("user_id", user["id"])
        .eq("status", "ready")
        .limit(1)
        .execute()
    )
    if doc_check.count and doc_check.count > 0:
        user_token = user["token"]

        async def retrieve_fn(query: str) -> list[dict]:
            return await retrieve_chunks(query, user_token)

    async def event_generator():
        full_content = ""
        async for token in stream_chat_completion(messages_for_llm, thread_id=thread_id, user_id=user["id"], retrieve_fn=retrieve_fn):
            full_content += token
            yield {"data": json.dumps({"token": token})}

        # Save assistant message
        saved = (
            sb.table("messages")
            .insert(
                {
                    "thread_id": thread_id,
                    "user_id": user["id"],
                    "role": "assistant",
                    "content": full_content,
                }
            )
            .execute()
        )

        assistant_message = saved.data[0]

        # Auto-title if this is the first exchange (2 messages: user + assistant)
        all_messages = (
            sb.table("messages")
            .select("id", count="exact")
            .eq("thread_id", thread_id)
            .execute()
        )
        new_title = None
        if all_messages.count == 2:
            title_response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "user",
                        "content": f"Generate a brief title (3-6 words, no quotes) for a conversation that starts with: {request.content}",
                    }
                ],
            )
            new_title = (
                title_response.choices[0].message.content.strip().strip("\"'")
            )
            sb.table("threads").update({"title": new_title}).eq(
                "id", thread_id
            ).execute()

        final_data = {"done": True, "message": assistant_message}
        if new_title:
            final_data["new_title"] = new_title
        yield {"data": json.dumps(final_data, default=str)}

    return EventSourceResponse(event_generator())
