import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.core.repository import TenantOwnedMixin


class OrgLLMSettings(TenantOwnedMixin, Base):
    """Per-organization provider configuration. API keys are Fernet-encrypted
    — the plaintext only ever exists in memory while building a provider."""

    __tablename__ = "org_llm_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_provider: Mapped[str] = mapped_column(String(32), default="anthropic")
    chat_model: Mapped[str] = mapped_column(String(64), default="claude-sonnet-4-6")
    embedding_provider: Mapped[str] = mapped_column(String(32), default="voyage")
    anthropic_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    openai_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    voyage_api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("tenant_id"),)
