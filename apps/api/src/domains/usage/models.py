import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base
from src.core.repository import TenantOwnedMixin

FEATURE_CHAT = "chat"
FEATURE_RAG = "rag"
FEATURE_EXTRACTION = "extraction"
FEATURE_INGESTION = "ingestion"

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_DISCONNECTED = "disconnected"


class LLMUsage(TenantOwnedMixin, Base):
    """One row per LLM call — the source of truth for the usage dashboard.

    Append-only: rows are written even for failed or interrupted calls
    (status != ok), since provider cost is incurred regardless.
    """

    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feature: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=STATUS_OK)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_write_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # The dashboard's main access path: one tenant, a date range.
        Index("ix_llm_usage_tenant_created", "tenant_id", "created_at"),
    )
