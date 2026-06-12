"""Internal job endpoints — the Cloud Tasks push targets.

Every request must carry an OIDC token minted by Google for the queue's
service account, with this API as the audience. Anything else gets a 403.
Transient handler failures return 500 so the queue retries (max attempts
are configured on the queue itself).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Body, Depends, Request

from src.core.config import get_settings
from src.core.errors import ApiError, NotFound
from src.domains.documents.jobs import run_ingest_job

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal/jobs", tags=["internal"], include_in_schema=False)

JOB_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {
    "ingest_document_job": run_ingest_job,
}


class Forbidden403(ApiError):
    def __init__(self) -> None:
        super().__init__(403, "forbidden", "Invalid or missing job token")


def _verify_google_oidc(token: str, audience: str) -> dict[str, Any]:
    """Blocking verification (certificate fetch is cached by google-auth)."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        token, google_requests.Request(), audience
    )
    return dict(claims)


async def verify_internal_job_token(request: Request) -> None:
    settings = get_settings()
    expected_email = settings.jobs_service_account_email
    audience = (settings.internal_jobs_base_url or "").rstrip("/")
    if not expected_email or not audience:
        raise Forbidden403()

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Forbidden403()
    try:
        claims = await asyncio.to_thread(_verify_google_oidc, token, audience)
    except Exception as exc:
        logger.warning("internal_jobs.bad_token", error=str(exc))
        raise Forbidden403() from exc
    if claims.get("email") != expected_email or not claims.get("email_verified"):
        raise Forbidden403()


@router.post("/{job_name}", dependencies=[Depends(verify_internal_job_token)])
async def run_job(job_name: str, payload: Annotated[dict[str, Any], Body()]) -> dict[str, str]:
    handler = JOB_HANDLERS.get(job_name)
    if handler is None:
        raise NotFound(f"Unknown job {job_name!r}")
    logger.info("internal_jobs.run", job=job_name)
    await handler(**payload)
    return {"status": "ok"}
