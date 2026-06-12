import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tenancy import TenantContext
from src.domains.usage.models import (
    STATUS_DISCONNECTED,
    STATUS_ERROR,
    STATUS_OK,
    LLMUsage,
)
from src.domains.usage.repository import UsageRepository
from src.llm.pricing import cost_for
from src.llm.provider import ChatProvider
from src.llm.types import Completion, Message, StreamEnd, StreamEvent, ToolDef, Usage

logger = structlog.get_logger(__name__)

# Rough chars-per-token used to estimate output on interrupted streams —
# real usage never arrived, but the provider still billed the tokens.
CHARS_PER_TOKEN = 4


class UsageService:
    """Wraps provider calls so every one of them leaves an `llm_usage` row.

    Success paths flush (the request transaction commits as usual). Error and
    disconnect paths commit immediately: the request is dying, but the cost
    was incurred and must survive.
    """

    def __init__(self, db: AsyncSession, tenant: TenantContext):
        self._db = db
        self._repo = UsageRepository(db, tenant)
        self._tenant = tenant

    async def tracked_complete(
        self,
        provider: ChatProvider,
        feature: str,
        created_by: str,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        started = time.monotonic()
        try:
            completion = await provider.complete(messages, system, tools, json_schema, max_tokens)
        except Exception:
            await self._record(
                feature=feature,
                created_by=created_by,
                model="unknown",
                usage=Usage(),
                status=STATUS_ERROR,
                started=started,
                commit=True,
            )
            raise
        await self._record(
            feature=feature,
            created_by=created_by,
            model=completion.model,
            usage=completion.usage,
            status=STATUS_OK,
            started=started,
        )
        return completion

    async def tracked_stream(
        self,
        provider: ChatProvider,
        feature: str,
        created_by: str,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        streamed_chars = 0
        recorded = False
        try:
            async for event in provider.stream(messages, system, tools, max_tokens):
                if isinstance(event, StreamEnd):
                    await self._record(
                        feature=feature,
                        created_by=created_by,
                        model=event.completion.model,
                        usage=event.completion.usage,
                        status=STATUS_OK,
                        started=started,
                    )
                    recorded = True
                else:
                    streamed_chars += len(event.text)
                yield event
        except GeneratorExit:
            # Client disconnected mid-stream — estimate what was billed.
            if not recorded:
                await self._record_partial(
                    feature, created_by, streamed_chars, STATUS_DISCONNECTED, started
                )
            raise
        except Exception:
            if not recorded:
                await self._record_partial(
                    feature, created_by, streamed_chars, STATUS_ERROR, started
                )
            raise

    async def _record_partial(
        self, feature: str, created_by: str, streamed_chars: int, status: str, started: float
    ) -> None:
        estimated = Usage(output_tokens=streamed_chars // CHARS_PER_TOKEN)
        logger.warning(
            "usage.partial",
            feature=feature,
            status=status,
            estimated_output=estimated.output_tokens,
        )
        await self._record(
            feature=feature,
            created_by=created_by,
            model="unknown",
            usage=estimated,
            status=status,
            started=started,
            commit=True,
        )

    async def _record(
        self,
        feature: str,
        created_by: str,
        model: str,
        usage: Usage,
        status: str,
        started: float,
        commit: bool = False,
    ) -> LLMUsage:
        row = self._repo.add(
            LLMUsage(
                feature=feature,
                model=model,
                status=status,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=cost_for(model, usage),
                latency_ms=int((time.monotonic() - started) * 1000),
                created_by=created_by,
            )
        )
        if commit:
            await self._db.commit()
        else:
            await self._db.flush()
        return row
