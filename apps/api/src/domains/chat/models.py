import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.core.repository import TenantOwnedMixin


class Conversation(TenantOwnedMixin, Base):
    """Chat conversation skeleton — endpoints and messages land in SGS-025.

    Defined early as the first tenant-owned model proving the scoping layer.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
