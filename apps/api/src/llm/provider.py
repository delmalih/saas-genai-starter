from collections.abc import AsyncIterator
from typing import Any, Protocol

from src.llm.types import Completion, EmbeddingResult, Message, StreamEvent, ToolDef


class ChatProvider(Protocol):
    """Normalized chat interface — domain code depends on this, never on a
    concrete SDK. Implementations map provider errors to `src.llm.errors`."""

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion: ...

    def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


class EmbeddingProvider(Protocol):
    async def embed(
        self,
        texts: list[str],
        input_type: str = "document",  # "document" for ingestion, "query" for search
    ) -> EmbeddingResult: ...
