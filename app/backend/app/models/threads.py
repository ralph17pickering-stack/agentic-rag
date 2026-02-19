from pydantic import BaseModel
from datetime import datetime


class ThreadCreate(BaseModel):
    title: str = "New Chat"


class ThreadUpdate(BaseModel):
    title: str


class ThreadResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
