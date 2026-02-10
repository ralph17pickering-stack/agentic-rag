from pydantic import BaseModel
from datetime import datetime
from typing import Literal


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
    created_at: datetime
    updated_at: datetime
