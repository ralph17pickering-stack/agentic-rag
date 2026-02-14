from pydantic import BaseModel
from datetime import datetime
from typing import Literal


class UrlIngestRequest(BaseModel):
    url: str
    title: str | None = None


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    topics: list[str] | None = None
    document_date: str | None = None  # ISO date string YYYY-MM-DD, or None to clear


class DocumentResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    storage_path: str
    file_type: str
    file_size: int
    status: Literal["pending", "processing", "ready", "error"]
    error_message: str | None = None
    chunk_count: int
    content_hash: str | None = None
    extracted_text_path: str | None = None
    is_duplicate: bool = False
    title: str | None = None
    summary: str | None = None
    topics: list[str] = []
    document_date: str | None = None
    created_at: datetime
    updated_at: datetime
