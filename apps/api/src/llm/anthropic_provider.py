from collections.abc import AsyncIterator
from typing import Any

import anthropic

from src.llm.errors import (
    ContextTooLong,
    ProviderBadRequest,
    ProviderUnavailable,
    RateLimited,
)
from src.llm.types import (
    Completion,
    Message,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolDef,
    Usage,
)


def _retry_after_seconds(exc: anthropic.APIStatusError) -> float | None:
    value = exc.response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _map_error(exc: anthropic.APIError) -> Exception:
    if isinstance(exc, anthropic.RateLimitError):
        return RateLimited(retry_after=_retry_after_seconds(exc))
    if isinstance(exc, anthropic.InternalServerError):
        # Includes 529 overloaded_error.
        return ProviderUnavailable(str(exc))
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderUnavailable(str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        if "prompt is too long" in str(exc) or "context" in str(exc).lower():
            return ContextTooLong(str(exc))
        return ProviderBadRequest(str(exc))
    return ProviderBadRequest(str(exc))


class AnthropicProvider:
    """Claude chat provider.

    The SDK's built-in retries are disabled — resilience (retry, backoff,
    circuit breaker) lives in `src.llm.resilience`, provider-agnostic.
    """

    def __init__(self, api_key: str, model: str, default_max_tokens: int = 4096):
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)
        self._model = model
        self._default_max_tokens = default_max_tokens

    def _request_params(
        self,
        messages: list[Message],
        system: str | None,
        tools: list[ToolDef] | None,
        json_schema: dict[str, Any] | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens or self._default_max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            # Stable prefix → cacheable. Below the model's minimum cacheable
            # size this is silently ignored, so it's always safe to set.
            params["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        if tools:
            params["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        if json_schema:
            params["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        return params

    @staticmethod
    def _to_completion(message: anthropic.types.Message) -> Completion:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input) if block.input else {},
                    )
                )
        return Completion(
            text="".join(text_parts),
            stop_reason=message.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                cache_read_tokens=message.usage.cache_read_input_tokens or 0,
                cache_write_tokens=message.usage.cache_creation_input_tokens or 0,
            ),
            model=message.model,
            tool_calls=tool_calls,
        )

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        params = self._request_params(messages, system, tools, json_schema, max_tokens)
        try:
            response = await self._client.messages.create(**params)
        except anthropic.APIError as exc:
            raise _map_error(exc) from exc
        return self._to_completion(response)

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        params = self._request_params(messages, system, tools, None, max_tokens)
        try:
            async with self._client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text=text)
                final = await stream.get_final_message()
        except anthropic.APIError as exc:
            raise _map_error(exc) from exc
        yield StreamEnd(completion=self._to_completion(final))
