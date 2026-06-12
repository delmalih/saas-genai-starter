"""The OpenAI-compatible catalog entries (Gemini, Mistral, xAI, DeepSeek,
Groq, OpenRouter) all run through OpenAIProvider — these tests pin the two
things each entry actually contributes: the base_url requests are sent to
and the provider name surfaced in errors. Cohere has a native adapter."""

import json
from typing import Any

import httpx
import pytest
from src.llm.catalog import CHAT_PROVIDERS, EMBEDDING_PROVIDERS, PROVIDER_ANTHROPIC
from src.llm.cohere_provider import CohereEmbeddingProvider
from src.llm.errors import ProviderBadRequest
from src.llm.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
from src.llm.types import Message

OPENAI_COMPATIBLE_CHAT = [
    info for info in CHAT_PROVIDERS.values() if info.id != PROVIDER_ANTHROPIC
]


@pytest.mark.parametrize("info", OPENAI_COMPATIBLE_CHAT, ids=lambda i: i.id)
async def test_chat_provider_targets_its_base_url(info: Any) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(
            200,
            json={
                "model": info.default_model,
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    provider = OpenAIProvider(
        api_key="k",
        model=info.default_model,
        transport=httpx.MockTransport(handler),
        base_url=info.base_url or "https://api.openai.com/v1",
        provider_name=info.label,
    )
    completion = await provider.complete([Message(role="user", content="hi")])

    expected_base = (info.base_url or "https://api.openai.com/v1").rstrip("/")
    assert seen["url"] == f"{expected_base}/chat/completions"
    assert seen["model"] == info.default_model
    assert completion.text == "ok"


async def test_errors_carry_the_provider_label() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    provider = OpenAIProvider(
        api_key="k",
        model="mistral-small-latest",
        transport=httpx.MockTransport(handler),
        base_url="https://api.mistral.ai/v1",
        provider_name="Mistral",
    )
    with pytest.raises(ProviderBadRequest, match="Mistral returned 400"):
        await provider.complete([Message(role="user", content="hi")])


async def test_fixed_size_embedding_models_omit_dimensions() -> None:
    info = EMBEDDING_PROVIDERS["mistral"]
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": info.model,
                "data": [{"index": 0, "embedding": [0.1] * 1024}],
                "usage": {"prompt_tokens": 3},
            },
        )

    embedder = OpenAIEmbeddingProvider(
        api_key="k",
        model=info.model,
        dimensions=info.dimensions,
        transport=httpx.MockTransport(handler),
        base_url=info.base_url or "https://api.openai.com/v1",
        provider_name=info.label,
        send_dimensions=info.send_dimensions,
    )
    result = await embedder.embed(["hello"])

    assert seen["url"] == "https://api.mistral.ai/v1/embeddings"
    assert "dimensions" not in seen["payload"]
    assert len(result.embeddings[0]) == 1024


async def test_cohere_embeddings_map_request_and_response() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "embeddings": {"float": [[0.1] * 1024, [0.2] * 1024]},
                "meta": {"billed_units": {"input_tokens": 7}},
            },
        )

    embedder = CohereEmbeddingProvider(
        api_key="k", model="embed-v4.0", transport=httpx.MockTransport(handler)
    )
    result = await embedder.embed(["a", "b"], input_type="query")

    assert seen["url"] == "https://api.cohere.com/v2/embed"
    assert seen["payload"]["input_type"] == "search_query"
    assert seen["payload"]["output_dimension"] == 1024
    assert len(result.embeddings) == 2
    assert result.input_tokens == 7


def test_every_default_model_has_a_pricing_entry_or_is_openrouter() -> None:
    """Cost accounting silently records $0 for unknown models — keep that an
    explicit OpenRouter-only exception, not an accident."""
    from src.llm.pricing import PRICING

    for info in CHAT_PROVIDERS.values():
        if info.id == "openrouter":
            continue
        for model in info.models:
            assert model in PRICING, f"missing pricing for {info.id}:{model}"
    for embedding_info in EMBEDDING_PROVIDERS.values():
        assert embedding_info.model in PRICING, f"missing pricing for {embedding_info.model}"


def test_catalog_key_fields_exist_on_model_and_settings() -> None:
    """Each catalog key field needs its encrypted column and its env fallback
    attribute — this is the checklist a new provider PR must satisfy."""
    from src.core.config import Settings
    from src.domains.llm_settings.models import OrgLLMSettings
    from src.llm.catalog import KEY_FIELDS

    for key_field in KEY_FIELDS:
        assert hasattr(OrgLLMSettings, f"{key_field}_encrypted"), key_field
        assert key_field in Settings.model_fields, key_field
    for info in CHAT_PROVIDERS.values():
        assert info.key_field in KEY_FIELDS, info.id
    for embedding_info in EMBEDDING_PROVIDERS.values():
        assert embedding_info.key_field in KEY_FIELDS, embedding_info.id
