"""Smoke tests against the real APIs — skipped unless keys are present.

Run explicitly with: ANTHROPIC_API_KEY=... uv run pytest tests/llm/test_smoke.py
"""

import os

import pytest
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.types import Message, StreamEnd, TextDelta
from src.llm.voyage_provider import VoyageEmbeddingProvider

requires_anthropic = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"
)
requires_voyage = pytest.mark.skipif(
    not os.environ.get("VOYAGE_API_KEY"), reason="VOYAGE_API_KEY not set"
)


@requires_anthropic
async def test_real_completion() -> None:
    provider = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"], model="claude-sonnet-4-6")
    completion = await provider.complete(
        [Message(role="user", content="Reply with exactly: pong")], max_tokens=16
    )
    assert "pong" in completion.text.lower()
    assert completion.usage.input_tokens > 0
    assert completion.usage.output_tokens > 0


@requires_anthropic
async def test_real_streaming() -> None:
    provider = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"], model="claude-sonnet-4-6")
    deltas: list[str] = []
    final = None
    async for event in provider.stream(
        [Message(role="user", content="Count from 1 to 5, digits only.")], max_tokens=32
    ):
        if isinstance(event, TextDelta):
            deltas.append(event.text)
        elif isinstance(event, StreamEnd):
            final = event.completion
    assert deltas, "expected at least one text delta"
    assert final is not None
    assert final.usage.output_tokens > 0


@requires_voyage
async def test_real_embeddings() -> None:
    provider = VoyageEmbeddingProvider(api_key=os.environ["VOYAGE_API_KEY"], model="voyage-3.5")
    result = await provider.embed(["hello world", "bonjour le monde"])
    assert len(result.embeddings) == 2
    assert len(result.embeddings[0]) > 100
