import asyncio
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from app.dependencies import get_current_user
from app.services.supabase import get_supabase_client
from app.services.ingestion import ingest_document
from app.models.documents import DocumentResponse

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {"txt", "md"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("", response_model=list[DocumentResponse])
async def list_documents(user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    result = (
        sb.table("documents")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    # Upload to Supabase Storage
    storage_path = f"{user['id']}/{uuid.uuid4().hex}_{file.filename}"
    sb = get_supabase_client(user["token"])
    sb.storage.from_("documents").upload(
        storage_path, content, {"content-type": file.content_type or "text/plain"}
    )

    # Create document record
    doc = (
        sb.table("documents")
        .insert(
            {
                "user_id": user["id"],
                "filename": file.filename,
                "storage_path": storage_path,
                "file_type": ext,
                "file_size": len(content),
                "status": "pending",
            }
        )
        .execute()
    )
    document = doc.data[0]

    # Kick off background ingestion
    asyncio.create_task(
        ingest_document(document["id"], user["id"], storage_path)
    )

    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: dict = Depends(get_current_user),
):
    sb = get_supabase_client(user["token"])

    # Fetch document to get storage_path
    result = (
        sb.table("documents")
        .select("*")
        .eq("id", document_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    document = result.data[0]

    # Delete from storage (ignore errors if file already gone)
    try:
        sb.storage.from_("documents").remove([document["storage_path"]])
    except Exception:
        pass

    # Delete document (chunks cascade via FK)
    sb.table("documents").delete().eq("id", document_id).execute()
