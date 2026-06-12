from datetime import date

from pydantic import BaseModel


class DailyCostOut(BaseModel):
    day: date
    feature: str
    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    calls: int


class UsageLimitsOut(BaseModel):
    requests_per_minute: int
    tokens_per_day: int
    tokens_used_today: int


class UsageSummaryOut(BaseModel):
    total_cost_usd: float
    limits: UsageLimitsOut
