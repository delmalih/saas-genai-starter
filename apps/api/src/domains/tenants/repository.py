import uuid
from datetime import UTC, datetime

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.domains.tenants.models import Invitation, Membership, Organization


class TenantRepository:
    """Data access for the tenant domain itself — the one domain that is not
    tenant-scoped, since it defines what a tenant is."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_memberships_for_user(self, user_id: str) -> list[Membership]:
        # Eager-load the organization: lazy loading raises in async contexts.
        result = await self._db.execute(
            select(Membership)
            .where(Membership.user_id == user_id)
            .join(Organization)
            .options(joinedload(Membership.organization))
            .order_by(Organization.created_at)
        )
        return list(result.scalars().unique().all())

    async def get_membership(self, organization_id: uuid.UUID, user_id: str) -> Membership | None:
        result = await self._db.execute(
            select(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
            )
            .options(joinedload(Membership.organization))
        )
        return result.scalar_one_or_none()

    async def list_members(self, organization_id: uuid.UUID) -> list[Membership]:
        result = await self._db.execute(
            select(Membership)
            .where(Membership.organization_id == organization_id)
            .order_by(Membership.created_at)
        )
        return list(result.scalars().all())

    async def get_organization(self, organization_id: uuid.UUID) -> Organization | None:
        return await self._db.get(Organization, organization_id)

    async def create_organization(self, name: str, owner_user_id: str) -> Organization:
        organization = Organization(name=name)
        organization.memberships.append(Membership(user_id=owner_user_id, role="owner"))
        self._db.add(organization)
        await self._db.flush()
        return organization

    async def delete_membership(self, membership: Membership) -> None:
        await self._db.delete(membership)
        await self._db.flush()

    def add_membership(self, membership: Membership) -> Membership:
        self._db.add(membership)
        return membership

    async def add_invitation(self, invitation: Invitation) -> Invitation:
        self._db.add(invitation)
        await self._db.flush()
        # Load server-generated defaults (created_at) before serialization.
        await self._db.refresh(invitation)
        return invitation

    async def get_invitation(
        self, organization_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> Invitation | None:
        result = await self._db.execute(
            select(Invitation).where(
                Invitation.organization_id == organization_id,
                Invitation.id == invitation_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        result = await self._db.execute(
            select(Invitation)
            .where(Invitation.token_hash == token_hash)
            .options(joinedload(Invitation.organization))
        )
        return result.scalar_one_or_none()

    async def list_pending_invitations(self, organization_id: uuid.UUID) -> list[Invitation]:
        result = await self._db.execute(
            select(Invitation)
            .where(
                Invitation.organization_id == organization_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
            .order_by(Invitation.created_at)
        )
        return list(result.scalars().all())

    async def resolve_users(self, user_ids: list[str]) -> dict[str, dict[str, str | None]]:
        """Read-only lookup of user profiles from the Better Auth schema.

        Same database, different schema — the auth service owns writes,
        the API only ever reads.
        """
        if not user_ids:
            return {}
        statement = text('SELECT id, email, name FROM auth."user" WHERE id IN :ids').bindparams(
            bindparam("ids", expanding=True)
        )
        result = await self._db.execute(statement, {"ids": user_ids})
        return {row.id: {"email": row.email, "name": row.name} for row in result}
