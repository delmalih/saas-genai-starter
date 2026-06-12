import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentStatus = Literal["uploaded", "processing", "ready", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    name: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None
    title: str | None
    language: str | None
    summary: str | None
    topics: list[str] | None
    created_at: datetime
