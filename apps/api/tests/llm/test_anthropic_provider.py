from typing import Any

import anthropic
import httpx
import pytest
from anthropic.types import Message as SDKMessage
from anthropic.types import TextBlock, ToolUseBlock
from anthropic.types import Usage as SDKUsage
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.errors import ContextTooLong, ProviderUnavailable, RateLimited
from src.llm.types import Message, ToolDef


def sdk_message(**overrides: Any) -> SDKMessage:
    defaults: dict[str, Any] = {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "content": [TextBlock(type="text", text="Hello!")],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": SDKUsage(
            input_tokens=100,
            output_tokens=20,
            cache_read_input_tokens=80,
            cache_creation_input_tokens=15,
        ),
    }
    defaults.update(overrides)
    return SDKMessage(**defaults)


class StubMessages:
    def __init__(self, response: SDKMessage | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.last_params: dict[str, Any] = {}

    async def create(self, **params: Any) -> SDKMessage:
        self.last_params = params
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.fixture
def provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key", model="claude-sonnet-4-6")


def stub(provider: AnthropicProvider, **kwargs: Any) -> StubMessages:
    stub_messages = StubMessages(**kwargs)
    provider._client.messages = stub_messages  # type: ignore[assignment]
    return stub_messages


async def test_maps_text_and_usage(provider: AnthropicProvider) -> None:
    stub(provider, response=sdk_message())

    completion = await provider.complete([Message(role="user", content="hi")])

    assert completion.text == "Hello!"
    assert completion.stop_reason == "end_turn"
    assert completion.usage.input_tokens == 100
    assert completion.usage.cache_read_tokens == 80
    assert completion.usage.cache_write_tokens == 15


async def test_maps_tool_calls(provider: AnthropicProvider) -> None:
    stub(
        provider,
        response=sdk_message(
            content=[
                TextBlock(type="text", text="Let me search."),
                ToolUseBlock(
                    type="tool_use",
                    id="toolu_1",
                    name="search_documents",
                    input={"query": "pricing"},
                ),
            ],
            stop_reason="tool_use",
        ),
    )

    completion = await provider.complete(
        [Message(role="user", content="find pricing")],
        tools=[ToolDef(name="search_documents", description="Search", input_schema={})],
    )

    assert completion.stop_reason == "tool_use"
    assert completion.tool_calls[0].name == "search_documents"
    assert completion.tool_calls[0].arguments == {"query": "pricing"}


async def test_system_prompt_gets_cache_control(provider: AnthropicProvider) -> None:
    stub_messages = stub(provider, response=sdk_message())

    await provider.complete([Message(role="user", content="hi")], system="You are helpful.")

    system = stub_messages.last_params["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def _api_error(
    cls: type[anthropic.APIStatusError], status: int, message: str, headers: dict[str, str]
) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request, headers=headers)
    return cls(message=message, response=response, body={"error": {"message": message}})


async def test_rate_limit_maps_with_retry_after(provider: AnthropicProvider) -> None:
    error = _api_error(anthropic.RateLimitError, 429, "rate limited", {"retry-after": "7"})
    stub(provider, error=error)

    with pytest.raises(RateLimited) as exc_info:
        await provider.complete([Message(role="user", content="hi")])
    assert exc_info.value.retry_after == 7.0


async def test_overloaded_maps_to_unavailable(provider: AnthropicProvider) -> None:
    error = _api_error(anthropic.InternalServerError, 529, "overloaded_error", {})
    stub(provider, error=error)

    with pytest.raises(ProviderUnavailable):
        await provider.complete([Message(role="user", content="hi")])


async def test_context_too_long_maps(provider: AnthropicProvider) -> None:
    error = _api_error(anthropic.BadRequestError, 400, "prompt is too long: 250000 tokens", {})
    stub(provider, error=error)

    with pytest.raises(ContextTooLong):
        await provider.complete([Message(role="user", content="huge")])
