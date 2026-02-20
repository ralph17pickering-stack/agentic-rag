import asyncio
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, File, status
from starlette.datastructures import UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from app.dependencies import get_current_user
from app.services.supabase import get_supabase_client, get_service_supabase_client
from app.services.ingestion import ingest_document
from app.services.hashing import sha256_hex
from app.services.extraction import extract_text
from app.models.documents import DocumentResponse, UrlIngestRequest, DocumentUpdateRequest
from pydantic import BaseModel as PydanticBaseModel


class BlockTagRequest(PydanticBaseModel):
    tag: str

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


@router.get("/blocked-tags")
async def list_blocked_tags(user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    try:
        result = sb.table("blocked_tags").select("*").order("created_at", desc=True).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list blocked tags: {e}")
    return result.data


@router.post("/blocked-tags")
async def block_tag(body: BlockTagRequest, user: dict = Depends(get_current_user)):
    tag = body.tag.strip().lower()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")
    sb = get_supabase_client(user["token"])
    try:
        result = sb.rpc("block_tag", {"p_tag": tag}).execute()
        docs_updated = result.data if isinstance(result.data, int) else 0
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to block tag: {e}")
    return {"tag": tag, "documents_updated": docs_updated}


@router.delete("/blocked-tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_tag(tag: str, user: dict = Depends(get_current_user)):
    sb = get_supabase_client(user["token"])
    try:
        sb.rpc("unblock_tag", {"p_tag": tag}).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unblock tag: {e}")


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document_metadata(
    document_id: str,
    body: DocumentUpdateRequest,
    user: dict = Depends(get_current_user),
):
    sb = get_supabase_client(user["token"])
    existing = sb.table("documents").select("*").eq("id", document_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Document not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return existing.data[0]

    result = sb.table("documents").update(updates).eq("id", document_id).execute()
    return result.data[0]


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


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user: dict = Depends(get_current_user),
):
    sb = get_supabase_client(user["token"])
    res = (
        sb.table("documents")
        .select("*")
        .eq("id", document_id)
        .eq("user_id", user["id"])
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**res.data)


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    user: dict = Depends(get_current_user),
):
    sb = get_supabase_client(user["token"])
    result = sb.table("documents").select("*").eq("id", document_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")

    document = result.data[0]
    if document["status"] != "ready":
        raise HTTPException(status_code=400, detail="Document is not ready")

    service_sb = get_service_supabase_client()

    # If extracted text exists, return it directly
    if document.get("extracted_text_path"):
        text_bytes = service_sb.storage.from_("documents").download(
            document["extracted_text_path"]
        )
        return PlainTextResponse(text_bytes.decode("utf-8"))

    # Fallback for legacy documents: re-extract from original file
    file_bytes = service_sb.storage.from_("documents").download(
        document["storage_path"]
    )
    text = extract_text(file_bytes, document["file_type"])

    # Cache for future requests
    extracted_path = f"{user['id']}/{document_id}_extracted.txt"
    service_sb.storage.from_("documents").upload(
        extracted_path,
        text.encode("utf-8"),
        {"content-type": "text/plain; charset=utf-8"},
    )
    sb.table("documents").update(
        {"extracted_text_path": extracted_path}
    ).eq("id", document_id).execute()

    return PlainTextResponse(text)


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
        paths_to_remove = [document["storage_path"]]
        if document.get("extracted_text_path"):
            paths_to_remove.append(document["extracted_text_path"])
        service_sb.storage.from_("documents").remove(paths_to_remove)
    except Exception:
        pass

    # Delete document (chunks cascade via FK)
    sb.table("documents").delete().eq("id", document_id).execute()


@router.post("/backfill-graph")
async def backfill_graph(user: dict = Depends(get_current_user)):
    """Re-run graph extraction for all ready documents belonging to the current user."""
    from app.services.graph_extractor import extract_graph_for_document
    sb = get_supabase_client(user["token"])
    service_sb = get_service_supabase_client()

    docs = (
        sb.table("documents")
        .select("id")
        .eq("status", "ready")
        .execute()
    ).data

    processed = 0
    errors = 0
    for doc in docs:
        doc_id = doc["id"]
        try:
            chunk_rows = [
                {"id": r["id"], "content": r["content"]}
                for r in service_sb.table("chunks").select("id,content")
                             .eq("document_id", doc_id).execute().data
            ]
            await extract_graph_for_document(doc_id, user["id"], chunk_rows)
            processed += 1
        except Exception:
            errors += 1

    return {"processed": processed, "errors": errors}


@router.post("/from-url")
async def ingest_from_url(
    body: UrlIngestRequest,
    user: dict = Depends(get_current_user),
):
    # Fetch URL content
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            resp = await http.get(body.url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    content = resp.content
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="URL returned empty content")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Content exceeds 10 MB limit")

    content_hash = sha256_hex(content)
    sb = get_supabase_client(user["token"])

    # Check for exact duplicate
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

    filename = body.title or body.url
    storage_path = f"{user['id']}/{uuid.uuid4().hex}_{filename[:80]}.html"

    # Upload to storage via service role
    service_sb = get_service_supabase_client()
    service_sb.storage.from_("documents").upload(
        storage_path, content, {"content-type": "text/html"}
    )

    # Create document record
    doc = (
        sb.table("documents")
        .insert(
            {
                "user_id": user["id"],
                "filename": filename,
                "storage_path": storage_path,
                "file_type": "html",
                "file_size": len(content),
                "content_hash": content_hash,
                "status": "pending",
                "source_url": body.url,
            }
        )
        .execute()
    )
    document = doc.data[0]

    # Background ingestion
    asyncio.create_task(
        ingest_document(document["id"], user["id"], storage_path, "html")
    )

    return JSONResponse(content=document, status_code=201)
