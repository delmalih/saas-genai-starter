import pytest
from src.llm.errors import CircuitOpen, ProviderBadRequest, ProviderUnavailable, RateLimited
from src.llm.resilience import CircuitBreaker, ResilientChatProvider, RetryPolicy
from src.llm.types import Message, StreamEnd, TextDelta

from tests.llm.fakes import FakeChatProvider

FAST = RetryPolicy(max_attempts=3, base_delay=0.001, max_delay=0.002)
USER_MESSAGE = [Message(role="user", content="hi")]


async def test_retries_transient_errors_then_succeeds() -> None:
    fake = FakeChatProvider(errors=[ProviderUnavailable("boom"), RateLimited()])
    provider = ResilientChatProvider(fake, policy=FAST)

    completion = await provider.complete(USER_MESSAGE)

    assert completion.text == "ok"
    assert fake.calls == 3


async def test_gives_up_after_max_attempts() -> None:
    fake = FakeChatProvider(errors=[ProviderUnavailable("boom")] * 5)
    provider = ResilientChatProvider(fake, policy=FAST)

    with pytest.raises(ProviderUnavailable):
        await provider.complete(USER_MESSAGE)
    assert fake.calls == FAST.max_attempts


async def test_non_retryable_errors_propagate_immediately() -> None:
    fake = FakeChatProvider(errors=[ProviderBadRequest("bad schema")])
    provider = ResilientChatProvider(fake, policy=FAST)

    with pytest.raises(ProviderBadRequest):
        await provider.complete(USER_MESSAGE)
    assert fake.calls == 1


async def test_breaker_opens_after_consecutive_failures() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=3, recovery_seconds=30, clock=lambda: now[0])
    fake = FakeChatProvider(errors=[ProviderUnavailable("down")] * 10)
    provider = ResilientChatProvider(fake, policy=FAST, breaker=breaker)

    with pytest.raises(ProviderUnavailable):
        await provider.complete(USER_MESSAGE)

    # Breaker is now open: calls fail fast without reaching the provider.
    calls_before = fake.calls
    with pytest.raises(CircuitOpen):
        await provider.complete(USER_MESSAGE)
    assert fake.calls == calls_before


async def test_breaker_half_open_probe_recovers() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=30, clock=lambda: now[0])
    fake = FakeChatProvider(errors=[ProviderUnavailable("down")] * 2)
    provider = ResilientChatProvider(
        fake, policy=RetryPolicy(max_attempts=2, base_delay=0.001), breaker=breaker
    )

    with pytest.raises(ProviderUnavailable):
        await provider.complete(USER_MESSAGE)
    with pytest.raises(CircuitOpen):
        await provider.complete(USER_MESSAGE)

    # After the recovery window, one probe goes through and closes the circuit.
    now[0] = 31.0
    completion = await provider.complete(USER_MESSAGE)
    assert completion.text == "ok"

    completion = await provider.complete(USER_MESSAGE)
    assert completion.text == "ok"


async def test_stream_retries_before_first_event() -> None:
    fake = FakeChatProvider(errors=[ProviderUnavailable("boom")])
    provider = ResilientChatProvider(fake, policy=FAST)

    events = [event async for event in provider.stream(USER_MESSAGE)]

    assert fake.calls == 2
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["hel", "lo"]
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].completion.usage.input_tokens == 10


async def test_retry_respects_retry_after() -> None:
    policy = RetryPolicy(max_attempts=2, base_delay=5.0, max_delay=10.0)
    assert policy.delay_for(0, retry_after=0.001) == 0.001
    # Without retry-after, delay is jittered within the exponential bound.
    assert 0 <= policy.delay_for(1, retry_after=None) <= 10.0
