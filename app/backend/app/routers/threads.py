from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.services.supabase import get_supabase_client
from app.models.threads import ThreadCreate, ThreadUpdate, ThreadResponse

router = APIRouter(prefix="/api/threads", tags=["threads"])


@router.get("", response_model=list[ThreadResponse])
async def list_threads(user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    result = sb.table("threads").select("*").order("updated_at", desc=True).execute()
    return result.data


@router.post("", response_model=ThreadResponse, status_code=201)
async def create_thread(
    request: ThreadCreate, user: dict = Depends(get_current_user)
):
    sb = get_supabase_client(user["token"])
    result = (
        sb.table("threads")
        .insert({"user_id": user["id"], "title": request.title})
        .execute()
    )
    return result.data[0]


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str, request: ThreadUpdate, user: dict = Depends(get_current_user)
):
    sb = get_supabase_client(user["token"])
    result = (
        sb.table("threads")
        .update({"title": request.title})
        .eq("id", thread_id)
        .execute()
    )
    return result.data[0]


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    sb.table("threads").delete().eq("id", thread_id).execute()


@router.delete("/{thread_id}/messages", status_code=204)
async def clear_thread_messages(thread_id: str, user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    sb.table("messages").delete().eq("thread_id", thread_id).execute()
