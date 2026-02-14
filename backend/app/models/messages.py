from pydantic import BaseModel
from datetime import datetime
from typing import Any, Literal, Optional


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    user_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    web_results: Optional[list[dict[str, Any]]] = None
