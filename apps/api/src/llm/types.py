from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    """A normalized chat message.

    `content` is either plain text or a list of provider-shaped content blocks
    (used for tool results and multimodal turns).
    """

    role: Role
    content: str | list[dict[str, Any]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    text: str
    stop_reason: str  # end_turn | tool_use | max_tokens | refusal
    usage: Usage
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class StreamEnd:
    """Last event of every stream — carries the full completion (incl. usage)."""

    completion: Completion


StreamEvent = TextDelta | StreamEnd


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: list[list[float]]
    model: str
    input_tokens: int
