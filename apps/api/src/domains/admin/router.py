"""Platform admin endpoints — cross-tenant BY DESIGN.

Access is restricted to the ADMIN_EMAILS allowlist; everyone else gets a
404 (not a 403) so the surface stays invisible. This is the only module
allowed to query tenant-owned tables without a TenantContext.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.core.auth import AuthenticatedUser, get_current_user
from src.core.config import get_settings
from src.core.db import DbSession
from src.core.errors import NotFound
from src.domains.chat.models import Conversation
from src.domains.documents.models import Document
from src.domains.tenants.models import Membership, Organization
from src.domains.usage.models import LLMUsage

router = APIRouter(prefix="/admin", tags=["admin"])

COST_WINDOW_DAYS = 30


async def require_platform_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    allowlist = get_settings().admin_email_set
    if not user.email or user.email.lower() not in allowlist:
        # 404 — the admin surface does not exist for non-admins.
        raise NotFound("Not found")
    return user


PlatformAdmin = Annotated[AuthenticatedUser, Depends(require_platform_admin)]


class AdminOrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    members: int
    documents: int
    conversations: int
    cost_30d_usd: float
    rate_limit_rpm_override: int | None
    rate_limit_tpd_override: int | None


class LimitsUpdate(BaseModel):
    """None clears the override (server defaults apply again)."""

    requests_per_minute: int | None = Field(default=None, ge=0, le=10_000)
    tokens_per_day: int | None = Field(default=None, ge=0, le=100_000_000)


async def _counts_by_org(db: DbSession, model: type) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(model.tenant_id, func.count()).group_by(model.tenant_id)  # type: ignore[attr-defined]
    )
    return {row[0]: row[1] for row in rows.all()}


@router.get("/organizations")
async def list_all_organizations(admin: PlatformAdmin, db: DbSession) -> list[AdminOrganizationOut]:
    organizations = (
        (await db.execute(select(Organization).order_by(Organization.created_at))).scalars().all()
    )
    member_rows = await db.execute(
        select(Membership.organization_id, func.count()).group_by(Membership.organization_id)
    )
    members = {row[0]: row[1] for row in member_rows.all()}
    documents = await _counts_by_org(db, Document)
    conversations = await _counts_by_org(db, Conversation)

    window_start = datetime.now(UTC) - timedelta(days=COST_WINDOW_DAYS)
    cost_rows = await db.execute(
        select(LLMUsage.tenant_id, func.sum(LLMUsage.cost_usd))
        .where(LLMUsage.created_at >= window_start)
        .group_by(LLMUsage.tenant_id)
    )
    costs = {row[0]: row[1] for row in cost_rows.all()}

    return [
        AdminOrganizationOut(
            id=org.id,
            name=org.name,
            created_at=org.created_at,
            members=members.get(org.id, 0),
            documents=documents.get(org.id, 0),
            conversations=conversations.get(org.id, 0),
            cost_30d_usd=float(costs.get(org.id) or 0),
            rate_limit_rpm_override=org.rate_limit_rpm_override,
            rate_limit_tpd_override=org.rate_limit_tpd_override,
        )
        for org in organizations
    ]


@router.patch("/organizations/{organization_id}/limits")
async def update_organization_limits(
    organization_id: uuid.UUID,
    payload: LimitsUpdate,
    admin: PlatformAdmin,
    db: DbSession,
) -> AdminOrganizationOut:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise NotFound("Organization not found")
    organization.rate_limit_rpm_override = payload.requests_per_minute
    organization.rate_limit_tpd_override = payload.tokens_per_day
    await db.commit()
    return AdminOrganizationOut(
        id=organization.id,
        name=organization.name,
        created_at=organization.created_at,
        members=0,
        documents=0,
        conversations=0,
        cost_30d_usd=0,
        rate_limit_rpm_override=organization.rate_limit_rpm_override,
        rate_limit_tpd_override=organization.rate_limit_tpd_override,
    )
