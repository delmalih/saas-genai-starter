import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header

from src.core.auth import CurrentUser
from src.core.db import DbSession
from src.core.errors import BadRequest, NotFound


@dataclass(frozen=True)
class TenantContext:
    organization_id: uuid.UUID
    user_id: str
    role: str


async def get_current_tenant(
    user: CurrentUser,
    db: DbSession,
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> TenantContext:
    """Resolve the active organization from the X-Org-Id header and verify
    the caller's membership. Every tenant-scoped endpoint depends on this."""
    # Imported here to keep core free of domain imports at module load.
    from src.domains.tenants.repository import TenantRepository

    if not x_org_id:
        raise BadRequest("Missing X-Org-Id header")
    try:
        organization_id = uuid.UUID(x_org_id)
    except ValueError as exc:
        raise BadRequest("X-Org-Id must be a UUID") from exc

    membership = await TenantRepository(db).get_membership(organization_id, user.user_id)
    if membership is None:
        # 404, not 403 — don't reveal that the organization exists.
        raise NotFound("Organization not found")
    return TenantContext(
        organization_id=organization_id, user_id=user.user_id, role=membership.role
    )


CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]
