import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.core.auth import CurrentUser
from src.core.config import get_settings
from src.core.db import DbSession
from src.core.email import EmailSender, get_email_sender
from src.core.tenancy import CurrentTenant
from src.domains.tenants.models import Membership
from src.domains.tenants.schemas import (
    AcceptedInvitationOut,
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    MemberOut,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
)
from src.domains.tenants.service import TenantService

router = APIRouter(prefix="/organizations", tags=["organizations"])
invitations_router = APIRouter(prefix="/invitations", tags=["organizations"])


@invitations_router.post("/accept")
async def accept_invitation(
    payload: InvitationAccept, user: CurrentUser, db: DbSession
) -> AcceptedInvitationOut:
    membership = await TenantService(db).accept_invitation(user, payload.token)
    response = AcceptedInvitationOut(
        organization_id=membership.organization.id,
        organization_name=membership.organization.name,
        role=membership.role,  # type: ignore[arg-type]  # constrained by service rules
    )
    await db.commit()
    return response


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


@router.get("/current")
async def current_organization(tenant: CurrentTenant, db: DbSession) -> OrganizationOut:
    """Resolve the active organization from the X-Org-Id header."""
    membership = await TenantService(db).get_membership_for(tenant.organization_id, tenant.user_id)
    return to_organization_out(membership)


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


@router.post("/{organization_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    organization_id: uuid.UUID,
    payload: InvitationCreate,
    user: CurrentUser,
    db: DbSession,
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> InvitationOut:
    invitation, token = await TenantService(db).create_invitation(
        user, organization_id, payload.email, payload.role
    )
    response = InvitationOut.model_validate(invitation, from_attributes=True)
    await db.commit()

    invite_url = f"{get_settings().web_base_url}/invite/{token}"
    inviter = user.name or user.email or "A teammate"
    await email_sender.send(
        to=payload.email,
        subject=f"{inviter} invited you to join their workspace",
        text=(
            f"{inviter} invited you to collaborate.\n\n"
            f"Accept the invitation: {invite_url}\n\n"
            "This link is valid for 7 days and can be used once."
        ),
    )
    return response


@router.get("/{organization_id}/invitations")
async def list_invitations(
    organization_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[InvitationOut]:
    invitations = await TenantService(db).list_invitations(user, organization_id)
    return [
        InvitationOut.model_validate(invitation, from_attributes=True) for invitation in invitations
    ]


@router.delete(
    "/{organization_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    await TenantService(db).revoke_invitation(user, organization_id, invitation_id)
    await db.commit()
