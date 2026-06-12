from dataclasses import dataclass
from decimal import Decimal

import structlog

from src.llm.types import Usage

logger = structlog.get_logger(__name__)

MTOK = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens. Cache write priced at the 5-minute-TTL rate
    (1.25x input); cache read at 0.1x input."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cache_read_per_mtok: Decimal
    cache_write_per_mtok: Decimal


# Prices as of 2026-06 — https://platform.claude.com/docs/en/pricing and
# https://docs.voyageai.com/docs/pricing. Update here when providers change.
PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_write_per_mtok=Decimal("3.75"),
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=Decimal("1.00"),
        output_per_mtok=Decimal("5.00"),
        cache_read_per_mtok=Decimal("0.10"),
        cache_write_per_mtok=Decimal("1.25"),
    ),
    "claude-opus-4-8": ModelPricing(
        input_per_mtok=Decimal("5.00"),
        output_per_mtok=Decimal("25.00"),
        cache_read_per_mtok=Decimal("0.50"),
        cache_write_per_mtok=Decimal("6.25"),
    ),
    "voyage-3.5": ModelPricing(
        input_per_mtok=Decimal("0.06"),
        output_per_mtok=Decimal("0"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # OpenAI — verify against https://openai.com/api/pricing when bumping models.
    "gpt-5.1": ModelPricing(
        input_per_mtok=Decimal("1.25"),
        output_per_mtok=Decimal("10.00"),
        cache_read_per_mtok=Decimal("0.125"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "gpt-5.1-mini": ModelPricing(
        input_per_mtok=Decimal("0.25"),
        output_per_mtok=Decimal("2.00"),
        cache_read_per_mtok=Decimal("0.025"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "text-embedding-3-small": ModelPricing(
        input_per_mtok=Decimal("0.02"),
        output_per_mtok=Decimal("0"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # Google Gemini — https://ai.google.dev/pricing
    "gemini-3-pro-preview": ModelPricing(
        input_per_mtok=Decimal("2.00"),
        output_per_mtok=Decimal("12.00"),
        cache_read_per_mtok=Decimal("0.20"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "gemini-2.5-pro": ModelPricing(
        input_per_mtok=Decimal("1.25"),
        output_per_mtok=Decimal("10.00"),
        cache_read_per_mtok=Decimal("0.125"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "gemini-2.5-flash": ModelPricing(
        input_per_mtok=Decimal("0.30"),
        output_per_mtok=Decimal("2.50"),
        cache_read_per_mtok=Decimal("0.03"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "gemini-embedding-001": ModelPricing(
        input_per_mtok=Decimal("0.15"),
        output_per_mtok=Decimal("0"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # Mistral — https://mistral.ai/pricing
    "mistral-large-latest": ModelPricing(
        input_per_mtok=Decimal("2.00"),
        output_per_mtok=Decimal("6.00"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "mistral-medium-latest": ModelPricing(
        input_per_mtok=Decimal("0.40"),
        output_per_mtok=Decimal("2.00"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "mistral-small-latest": ModelPricing(
        input_per_mtok=Decimal("0.10"),
        output_per_mtok=Decimal("0.30"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "mistral-embed": ModelPricing(
        input_per_mtok=Decimal("0.10"),
        output_per_mtok=Decimal("0"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # xAI — https://docs.x.ai/docs/models
    "grok-4": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.75"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "grok-4-fast": ModelPricing(
        input_per_mtok=Decimal("0.20"),
        output_per_mtok=Decimal("0.50"),
        cache_read_per_mtok=Decimal("0.05"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # DeepSeek — https://api-docs.deepseek.com/quick_start/pricing
    "deepseek-chat": ModelPricing(
        input_per_mtok=Decimal("0.28"),
        output_per_mtok=Decimal("0.42"),
        cache_read_per_mtok=Decimal("0.028"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "deepseek-reasoner": ModelPricing(
        input_per_mtok=Decimal("0.28"),
        output_per_mtok=Decimal("0.42"),
        cache_read_per_mtok=Decimal("0.028"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # Groq — https://groq.com/pricing
    "llama-3.3-70b-versatile": ModelPricing(
        input_per_mtok=Decimal("0.59"),
        output_per_mtok=Decimal("0.79"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    "llama-3.1-8b-instant": ModelPricing(
        input_per_mtok=Decimal("0.05"),
        output_per_mtok=Decimal("0.08"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # Cohere — https://cohere.com/pricing
    "embed-v4.0": ModelPricing(
        input_per_mtok=Decimal("0.12"),
        output_per_mtok=Decimal("0"),
        cache_read_per_mtok=Decimal("0"),
        cache_write_per_mtok=Decimal("0"),
    ),
    # OpenRouter routes to many models with per-model pricing — usage is
    # recorded with $0 cost and a warning log (see cost_for below).
}


def cost_for(model: str, usage: Usage) -> Decimal:
    """Cost in USD for one call. Unknown models cost 0 and log a warning —
    better an under-counted dashboard than a broken request path."""
    pricing = PRICING.get(model)
    if pricing is None:
        logger.warning("pricing.unknown_model", model=model)
        return Decimal("0")
    cost = (
        usage.input_tokens * pricing.input_per_mtok
        + usage.output_tokens * pricing.output_per_mtok
        + usage.cache_read_tokens * pricing.cache_read_per_mtok
        + usage.cache_write_tokens * pricing.cache_write_per_mtok
    ) / MTOK
    return cost.quantize(Decimal("0.000001"))
