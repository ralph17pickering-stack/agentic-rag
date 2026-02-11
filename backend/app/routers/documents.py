import asyncio
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, File, status
from starlette.datastructures import UploadFile
from fastapi.responses import JSONResponse
from app.dependencies import get_current_user
from app.services.supabase import get_supabase_client, get_service_supabase_client
from app.services.ingestion import ingest_document
from app.services.hashing import sha256_hex
from app.models.documents import DocumentResponse

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {"txt", "md", "pdf", "docx", "csv", "html"}
CONTENT_TYPES = {
    "txt": "text/plain",
    "md": "text/markdown",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "html": "text/html",
}
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


@router.post("")
async def upload_document(
    request: Request,
    user: dict = Depends(get_current_user),
):
    # Parse multipart with 10MB part size limit (Starlette defaults to 1MB)
    form = await request.form(max_part_size=MAX_FILE_SIZE)
    file = form.get("file")
    if not isinstance(file, UploadFile):
        raise HTTPException(status_code=400, detail="No file provided")

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

    content_hash = sha256_hex(content)
    sb = get_supabase_client(user["token"])

    # Check for exact duplicate (same user + same content hash)
    existing = (
        sb.table("documents")
        .select("*")
        .eq("user_id", user["id"])
        .eq("content_hash", content_hash)
        .execute()
    )
    if existing.data:
        doc = existing.data[0]
        doc["is_duplicate"] = True
        return JSONResponse(content=doc, status_code=200)

    # Check for same filename → replace (delete old, insert new)
    same_name = (
        sb.table("documents")
        .select("*")
        .eq("user_id", user["id"])
        .eq("filename", file.filename)
        .execute()
    )
    service_sb = get_service_supabase_client()
    for old_doc in same_name.data:
        try:
            service_sb.storage.from_("documents").remove([old_doc["storage_path"]])
        except Exception:
            pass
        sb.table("documents").delete().eq("id", old_doc["id"]).execute()

    # Upload to Supabase Storage (service role bypasses storage RLS)
    storage_path = f"{user['id']}/{uuid.uuid4().hex}_{file.filename}"
    service_sb.storage.from_("documents").upload(
        storage_path, content, {"content-type": CONTENT_TYPES.get(ext, "application/octet-stream")}
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
                "content_hash": content_hash,
                "status": "pending",
            }
        )
        .execute()
    )
    document = doc.data[0]

    # Kick off background ingestion
    asyncio.create_task(
        ingest_document(document["id"], user["id"], storage_path, ext)
    )

    return JSONResponse(content=document, status_code=201)


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

    # Delete from storage (service role bypasses storage RLS)
    try:
        service_sb = get_service_supabase_client()
        service_sb.storage.from_("documents").remove([document["storage_path"]])
    except Exception:
        pass

    # Delete document (chunks cascade via FK)
    sb.table("documents").delete().eq("id", document_id).execute()
