import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime


class CitationOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    page: int | None = None
    snippet: str
    score: float | None = None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[CitationOut] | None = None
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[ChatMessageOut]


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
