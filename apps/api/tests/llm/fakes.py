from collections.abc import AsyncIterator
from typing import Any

from src.llm.errors import LLMError
from src.llm.types import (
    Completion,
    EmbeddingResult,
    Message,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolDef,
    Usage,
)


def make_completion(text: str = "ok", **overrides: Any) -> Completion:
    defaults: dict[str, Any] = {
        "text": text,
        "stop_reason": "end_turn",
        "usage": Usage(input_tokens=10, output_tokens=5),
        "model": "fake-model",
    }
    defaults.update(overrides)
    return Completion(**defaults)


class FakeChatProvider:
    """Scriptable provider.

    Behavior per call: raise the next queued error if any; otherwise return
    the next completion from `script` (sequential, e.g. a tool_use round then
    a final answer), falling back to `result` once the script is exhausted.
    Every call's kwargs are captured in `received` for assertions.
    """

    def __init__(
        self,
        result: Completion | None = None,
        errors: list[LLMError] | None = None,
        stream_chunks: list[str] | None = None,
        script: list[Completion] | None = None,
    ):
        self.result = result or make_completion()
        self.errors = errors or []
        self.stream_chunks = stream_chunks or ["hel", "lo"]
        self.script = list(script) if script else []
        self.calls = 0
        self.received: list[dict[str, Any]] = []

    def _next_error(self) -> LLMError | None:
        if self.errors:
            return self.errors.pop(0)
        return None

    def _next_completion(self) -> Completion:
        if self.script:
            return self.script.pop(0)
        return self.result

    def _record(self, **kwargs: Any) -> None:
        self.calls += 1
        self.received.append(kwargs)

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        self._record(messages=messages, system=system, tools=tools, json_schema=json_schema)
        error = self._next_error()
        if error:
            raise error
        return self._next_completion()

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self._record(messages=messages, system=system, tools=tools)
        error = self._next_error()
        if error:
            raise error
        completion = self._next_completion()
        if completion.stop_reason != "tool_use":
            for chunk in self.stream_chunks:
                yield TextDelta(text=chunk)
        yield StreamEnd(completion=completion)


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 8):
        self.dimension = dimension

    async def embed(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> EmbeddingResult:
        # Deterministic per-text vectors so retrieval tests are stable.
        return EmbeddingResult(
            embeddings=[
                [float((hash(text) + i) % 97) / 97 for i in range(self.dimension)] for text in texts
            ],
            model="fake-embeddings",
            input_tokens=sum(len(t.split()) for t in texts),
        )
