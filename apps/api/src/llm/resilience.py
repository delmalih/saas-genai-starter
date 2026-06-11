import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from src.llm.errors import CircuitOpen, LLMError
from src.llm.provider import ChatProvider
from src.llm.types import Completion, Message, StreamEvent, ToolDef

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 8.0

    def delay_for(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        exponential = min(self.base_delay * (2**attempt), self.max_delay)
        return random.uniform(0, exponential)  # noqa: S311 — jitter, not crypto


class CircuitBreaker:
    """Fails fast when the provider is consistently down.

    closed → open after `failure_threshold` consecutive failures;
    open → half-open after `recovery_seconds` (one probe call allowed);
    half-open → closed on success, back to open on failure.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    def check(self) -> None:
        if self._opened_at is None:
            return
        elapsed = self._clock() - self._opened_at
        if elapsed < self._recovery_seconds or self._probe_in_flight:
            raise CircuitOpen("LLM provider circuit is open")
        # Half-open: let exactly one probe through.
        self._probe_in_flight = True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None
        self._probe_in_flight = False

    def record_failure(self) -> None:
        self._probe_in_flight = False
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            if self._opened_at is None:
                logger.warning("llm.circuit_open", failures=self._consecutive_failures)
            self._opened_at = self._clock()


async def call_with_retries[T](
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    breaker: CircuitBreaker,
) -> T:
    last_error: LLMError | None = None
    for attempt in range(policy.max_attempts):
        breaker.check()
        try:
            result = await fn()
        except LLMError as exc:
            breaker.record_failure()
            if not exc.retryable:
                raise
            last_error = exc
            retry_after = getattr(exc, "retry_after", None)
            delay = policy.delay_for(attempt, retry_after)
            logger.warning("llm.retry", attempt=attempt + 1, delay=round(delay, 2), error=str(exc))
            await asyncio.sleep(delay)
        else:
            breaker.record_success()
            return result
    assert last_error is not None  # noqa: S101 — loop always sets it before exhausting
    raise last_error


class ResilientChatProvider:
    """ChatProvider decorator adding retries and a circuit breaker.

    Streams are only retried until the first event is yielded — once output
    has been surfaced to a client, replaying from scratch would duplicate it.
    """

    def __init__(
        self,
        inner: ChatProvider,
        policy: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
    ):
        self._inner = inner
        self._policy = policy or RetryPolicy()
        self._breaker = breaker or CircuitBreaker()

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        return await call_with_retries(
            lambda: self._inner.complete(messages, system, tools, json_schema, max_tokens),
            self._policy,
            self._breaker,
        )

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        for attempt in range(self._policy.max_attempts):
            self._breaker.check()
            iterator = aiter(self._inner.stream(messages, system, tools, max_tokens))
            try:
                first = await anext(iterator)
            except StopAsyncIteration:
                self._breaker.record_success()
                return
            except LLMError as exc:
                self._breaker.record_failure()
                if not exc.retryable or attempt == self._policy.max_attempts - 1:
                    raise
                retry_after = getattr(exc, "retry_after", None)
                await asyncio.sleep(self._policy.delay_for(attempt, retry_after))
                continue

            # First event received — past this point failures propagate.
            self._breaker.record_success()
            yield first
            async for event in iterator:
                yield event
            return
