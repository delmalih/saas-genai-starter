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
