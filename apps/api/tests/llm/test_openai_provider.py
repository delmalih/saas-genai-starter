import json
from typing import Any

import httpx
import pytest
from src.llm.errors import RateLimited
from src.llm.openai_provider import OpenAIEmbeddingProvider, OpenAIProvider
from src.llm.types import Message, StreamEnd, TextDelta, ToolDef


def chat_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def make_provider(handler: Any) -> OpenAIProvider:
    return OpenAIProvider(
        api_key="sk-test",
        model="gpt-5.1-mini",
        transport=httpx.MockTransport(handler),
    )


async def test_complete_maps_text_usage_and_cached_tokens() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return chat_response(
            {
                "model": "gpt-5.1-mini",
                "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 60},
                },
            }
        )

    completion = await make_provider(handler).complete(
        [Message(role="user", content="hi")], system="be brief"
    )

    assert completion.text == "Hello!"
    assert completion.stop_reason == "end_turn"
    assert completion.usage.input_tokens == 40  # prompt minus cached
    assert completion.usage.cache_read_tokens == 60
    # System prompt travels as the first message.
    assert captured["messages"][0] == {"role": "system", "content": "be brief"}


async def test_complete_maps_tool_calls_and_translates_history() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return chat_response(
            {
                "model": "gpt-5.1-mini",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_documents",
                                        "arguments": '{"query": "pricing"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )

    history = [
        Message(role="user", content="find pricing"),
        Message(
            role="assistant",
            content=[
                {"type": "text", "text": "Searching."},
                {
                    "type": "tool_use",
                    "id": "call_0",
                    "name": "search_documents",
                    "input": {"query": "x"},
                },
            ],
        ),
        Message(
            role="user",
            content=[{"type": "tool_result", "tool_use_id": "call_0", "content": "nothing"}],
        ),
    ]
    completion = await make_provider(handler).complete(
        history, tools=[ToolDef(name="search_documents", description="d", input_schema={})]
    )

    assert completion.stop_reason == "tool_use"
    assert completion.tool_calls[0].arguments == {"query": "pricing"}
    # Anthropic-shaped blocks were translated to OpenAI roles.
    sent = captured["messages"]
    assert sent[1]["tool_calls"][0]["function"]["name"] == "search_documents"
    assert sent[2] == {"role": "tool", "tool_call_id": "call_0", "content": "nothing"}


async def test_stream_parses_sse_and_assembles_usage() -> None:
    chunks = [
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}},
    ]
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    events = [
        event async for event in make_provider(handler).stream([Message(role="user", content="hi")])
    ]

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(deltas) == "Hello"
    end = events[-1]
    assert isinstance(end, StreamEnd)
    assert end.completion.usage.input_tokens == 7
    assert end.completion.stop_reason == "end_turn"


async def test_rate_limit_maps_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "3"}, json={})

    with pytest.raises(RateLimited) as exc_info:
        await make_provider(handler).complete([Message(role="user", content="hi")])
    assert exc_info.value.retry_after == 3.0


async def test_embeddings_request_pins_dimensions() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "text-embedding-3-small",
                "data": [
                    {"index": 1, "embedding": [0.2] * 1024},
                    {"index": 0, "embedding": [0.1] * 1024},
                ],
                "usage": {"prompt_tokens": 12},
            },
        )

    provider = OpenAIEmbeddingProvider(
        api_key="sk-test",
        model="text-embedding-3-small",
        dimensions=1024,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed(["a", "b"])

    assert captured["dimensions"] == 1024
    # Results re-ordered by index.
    assert result.embeddings[0][0] == 0.1
    assert result.input_tokens == 12
