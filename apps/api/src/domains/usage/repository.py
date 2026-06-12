from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from src.core.repository import TenantScopedRepository
from src.domains.usage.models import LLMUsage


@dataclass(frozen=True)
class DailyCost:
    day: date
    feature: str
    model: str
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    calls: int


class UsageRepository(TenantScopedRepository[LLMUsage]):
    model = LLMUsage

    async def daily_costs(self, start: datetime, end: datetime) -> list[DailyCost]:
        """Cost per day, feature and model for the active tenant."""
        day = func.date_trunc("day", LLMUsage.created_at).label("day")
        statement = (
            select(
                day,
                LLMUsage.feature,
                LLMUsage.model,
                func.sum(LLMUsage.cost_usd).label("cost_usd"),
                func.sum(LLMUsage.input_tokens).label("input_tokens"),
                func.sum(LLMUsage.output_tokens).label("output_tokens"),
                func.sum(LLMUsage.cache_read_tokens).label("cache_read_tokens"),
                func.sum(LLMUsage.cache_write_tokens).label("cache_write_tokens"),
                func.count().label("calls"),
            )
            .where(
                LLMUsage.tenant_id == self._tenant.organization_id,
                LLMUsage.created_at >= start,
                LLMUsage.created_at < end,
            )
            .group_by(day, LLMUsage.feature, LLMUsage.model)
            .order_by(day)
        )
        result = await self._db.execute(statement)
        return [
            DailyCost(
                day=row.day.date(),
                feature=row.feature,
                model=row.model,
                cost_usd=row.cost_usd,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cache_read_tokens=row.cache_read_tokens,
                cache_write_tokens=row.cache_write_tokens,
                calls=row.calls,
            )
            for row in result
        ]

    async def total_cost(self, start: datetime, end: datetime) -> Decimal:
        statement = select(func.coalesce(func.sum(LLMUsage.cost_usd), 0)).where(
            LLMUsage.tenant_id == self._tenant.organization_id,
            LLMUsage.created_at >= start,
            LLMUsage.created_at < end,
        )
        result = await self._db.execute(statement)
        return Decimal(result.scalar_one())
