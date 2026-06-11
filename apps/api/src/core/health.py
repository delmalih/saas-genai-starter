from fastapi import APIRouter
from sqlalchemy import text

from src.core.db import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(db: DbSession) -> dict[str, str]:
    """Readiness: the database is reachable."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
