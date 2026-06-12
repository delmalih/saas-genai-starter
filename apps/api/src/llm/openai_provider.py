import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from src.llm.errors import (
    ContextTooLong,
    ProviderBadRequest,
    ProviderUnavailable,
    RateLimited,
)
from src.llm.types import (
    Completion,
    EmbeddingResult,
    Message,
    StreamEnd,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolDef,
    Usage,
)

OPENAI_API_URL = "https://api.openai.com/v1"

_FINISH_REASONS = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def _map_status(status: int, body: str, headers: httpx.Headers) -> Exception:
    if status == 429:
        retry_after = headers.get("retry-after")
        return RateLimited(retry_after=float(retry_after) if retry_after else None)
    if status >= 500:
        return ProviderUnavailable(f"OpenAI returned {status}")
    if "context_length" in body or "maximum context length" in body:
        return ContextTooLong(body[:500])
    return ProviderBadRequest(f"OpenAI returned {status}: {body[:500]}")


def _map_usage(usage: dict[str, Any]) -> Usage:
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    return Usage(
        # Convention (Anthropic-style): input_tokens excludes cache reads.
        input_tokens=usage.get("prompt_tokens", 0) - cached,
        output_tokens=usage.get("completion_tokens", 0),
        cache_read_tokens=cached,
        cache_write_tokens=0,  # OpenAI has no cache-write premium
    )


def _translate_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    """Our normalized messages use Anthropic-shaped content blocks as the
    lingua franca — translate them to the OpenAI chat format."""
    result: list[dict[str, Any]] = []
    if system:
        result.append({"role": "system", "content": system})
    for message in messages:
        if isinstance(message.content, str):
            result.append({"role": message.role, "content": message.content})
            continue
        if message.role == "assistant":
            text = "".join(b.get("text", "") for b in message.content if b.get("type") == "text")
            tool_calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                }
                for b in message.content
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)
        else:
            for block in message.content:
                if block.get("type") == "tool_result":
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": str(block.get("content", "")),
                        }
                    )
    return result


class OpenAIProvider:
    """OpenAI chat provider over plain httpx — same protocols as Anthropic."""

    def __init__(
        self,
        api_key: str,
        model: str,
        default_max_tokens: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._default_max_tokens = default_max_tokens
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=120,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _payload(
        self,
        messages: list[Message],
        system: str | None,
        tools: list[ToolDef] | None,
        json_schema: dict[str, Any] | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_completion_tokens": max_tokens or self._default_max_tokens,
            "messages": _translate_messages(messages, system),
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": json_schema, "strict": True},
            }
        return payload

    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        json_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        async with self._client() as client:
            try:
                response = await client.post(
                    f"{OPENAI_API_URL}/chat/completions",
                    json=self._payload(messages, system, tools, json_schema, max_tokens),
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise _map_status(response.status_code, response.text, response.headers)

        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        tool_calls = [
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=json.loads(call["function"]["arguments"] or "{}"),
            )
            for call in message.get("tool_calls") or []
        ]
        return Completion(
            text=message.get("content") or "",
            stop_reason=_FINISH_REASONS.get(choice.get("finish_reason", ""), "end_turn"),
            usage=_map_usage(data.get("usage") or {}),
            model=data.get("model", self._model),
            tool_calls=tool_calls,
        )

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolDef] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        payload = self._payload(messages, system, tools, None, max_tokens)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

        text_parts: list[str] = []
        tool_accumulator: dict[int, dict[str, str]] = {}
        finish_reason = ""
        usage = Usage()

        async with self._client() as client:
            try:
                async with client.stream(
                    "POST", f"{OPENAI_API_URL}/chat/completions", json=payload
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode()
                        raise _map_status(response.status_code, body, response.headers)
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[len("data: ") :]
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        if chunk.get("usage"):
                            usage = _map_usage(chunk["usage"])
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        if delta.get("content"):
                            text_parts.append(delta["content"])
                            yield TextDelta(text=delta["content"])
                        for call in delta.get("tool_calls") or []:
                            slot = tool_accumulator.setdefault(
                                call["index"], {"id": "", "name": "", "arguments": ""}
                            )
                            if call.get("id"):
                                slot["id"] = call["id"]
                            function = call.get("function") or {}
                            slot["name"] += function.get("name") or ""
                            slot["arguments"] += function.get("arguments") or ""
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(str(exc)) from exc

        tool_calls = [
            ToolCall(
                id=slot["id"],
                name=slot["name"],
                arguments=json.loads(slot["arguments"] or "{}"),
            )
            for _, slot in sorted(tool_accumulator.items())
        ]
        yield StreamEnd(
            completion=Completion(
                text="".join(text_parts),
                stop_reason=_FINISH_REASONS.get(finish_reason, "end_turn"),
                usage=usage,
                model=self._model,
                tool_calls=tool_calls,
            )
        )


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int = 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._transport = transport

    async def embed(
        self,
        texts: list[str],
        input_type: str = "document",  # OpenAI has no query/document distinction
    ) -> EmbeddingResult:
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            try:
                response = await client.post(
                    f"{OPENAI_API_URL}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "input": texts,
                        "dimensions": self._dimensions,
                    },
                )
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise _map_status(response.status_code, response.text, response.headers)
        payload = response.json()
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return EmbeddingResult(
            embeddings=[item["embedding"] for item in ordered],
            model=payload.get("model", self._model),
            input_tokens=(payload.get("usage") or {}).get("prompt_tokens", 0),
        )
