from pydantic import BaseModel
from datetime import datetime
from typing import Literal


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    user_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
