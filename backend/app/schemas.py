from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    pass


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None = None
    memory_summary: str | None = None
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    agent: str | None = None
    timestamp: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    filename: str
    uploaded_at: datetime


class ChatRequest(BaseModel):
    message: str
