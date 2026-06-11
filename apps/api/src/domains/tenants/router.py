import uuid

from fastapi import APIRouter, status

from src.core.auth import CurrentUser
from src.core.db import DbSession
from src.domains.tenants.models import Membership
from src.domains.tenants.schemas import (
    MemberOut,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
)
from src.domains.tenants.service import TenantService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def to_organization_out(membership: Membership) -> OrganizationOut:
    return OrganizationOut(
        id=membership.organization.id,
        name=membership.organization.name,
        role=membership.role,  # type: ignore[arg-type]  # constrained by service rules
        created_at=membership.organization.created_at,
    )


@router.get("")
async def list_organizations(user: CurrentUser, db: DbSession) -> list[OrganizationOut]:
    memberships = await TenantService(db).list_organizations(user)
    await db.commit()
    return [to_organization_out(m) for m in memberships]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate, user: CurrentUser, db: DbSession
) -> OrganizationOut:
    membership = await TenantService(db).create_organization(user, payload.name)
    response = to_organization_out(membership)
    await db.commit()
    return response


@router.patch("/{organization_id}")
async def rename_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    user: CurrentUser,
    db: DbSession,
) -> OrganizationOut:
    service = TenantService(db)
    await service.rename_organization(user, organization_id, payload.name)
    membership = await service.list_organizations(user)
    response = next(
        to_organization_out(m) for m in membership if m.organization_id == organization_id
    )
    await db.commit()
    return response


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[MemberOut]:
    members, profiles = await TenantService(db).list_members(user, organization_id)
    return [
        MemberOut(
            user_id=m.user_id,
            role=m.role,  # type: ignore[arg-type]  # constrained by service rules
            email=profiles.get(m.user_id, {}).get("email"),
            name=profiles.get(m.user_id, {}).get("name"),
        )
        for m in members
    ]


@router.patch("/{organization_id}/members/{member_user_id}")
async def update_member_role(
    organization_id: uuid.UUID,
    member_user_id: str,
    payload: MemberRoleUpdate,
    user: CurrentUser,
    db: DbSession,
) -> MemberOut:
    membership = await TenantService(db).update_member_role(
        user, organization_id, member_user_id, payload.role
    )
    response = MemberOut(
        user_id=membership.user_id,
        role=membership.role,  # type: ignore[arg-type]
        email=None,
        name=None,
    )
    await db.commit()
    return response


@router.delete(
    "/{organization_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    organization_id: uuid.UUID,
    member_user_id: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    await TenantService(db).remove_member(user, organization_id, member_user_id)
    await db.commit()
