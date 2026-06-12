from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.db import DbSession
from src.core.errors import BadRequest
from src.core.tenancy import CurrentTenant
from src.domains.usage.repository import UsageRepository
from src.domains.usage.schemas import DailyCostOut, UsageLimitsOut, UsageSummaryOut
from src.llm.rate_limit import TenantRateLimiter, get_rate_limiter

router = APIRouter(prefix="/usage", tags=["usage"])

RateLimiter = Annotated[TenantRateLimiter, Depends(get_rate_limiter)]

DEFAULT_RANGE_DAYS = 30


def resolve_range(start: date | None, end: date | None) -> tuple[datetime, datetime]:
    """[start, end] as an inclusive date range, defaulting to the last 30 days."""
    end_date = end or datetime.now(UTC).date()
    start_date = start or end_date - timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start_date > end_date:
        raise BadRequest("start must be before end")
    return (
        datetime.combine(start_date, time.min, tzinfo=UTC),
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC),
    )


@router.get("/daily")
async def daily_usage(
    tenant: CurrentTenant,
    db: DbSession,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> list[DailyCostOut]:
    range_start, range_end = resolve_range(start, end)
    daily = await UsageRepository(db, tenant).daily_costs(range_start, range_end)
    return [
        DailyCostOut(
            day=entry.day,
            feature=entry.feature,
            model=entry.model,
            cost_usd=float(entry.cost_usd),
            input_tokens=entry.input_tokens,
            output_tokens=entry.output_tokens,
            cache_read_tokens=entry.cache_read_tokens,
            cache_write_tokens=entry.cache_write_tokens,
            calls=entry.calls,
        )
        for entry in daily
    ]


@router.get("/summary")
async def usage_summary(
    tenant: CurrentTenant,
    db: DbSession,
    limiter: RateLimiter,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> UsageSummaryOut:
    range_start, range_end = resolve_range(start, end)
    total = await UsageRepository(db, tenant).total_cost(range_start, range_end)
    requests_per_minute, tokens_per_day = limiter.limits
    used_today = await limiter.tokens_used_today(tenant.organization_id)
    return UsageSummaryOut(
        total_cost_usd=float(total),
        limits=UsageLimitsOut(
            requests_per_minute=requests_per_minute,
            tokens_per_day=tokens_per_day,
            tokens_used_today=used_today,
        ),
    )
