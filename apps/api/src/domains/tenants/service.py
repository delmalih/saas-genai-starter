import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import AuthenticatedUser
from src.core.errors import Conflict, Forbidden, NotFound
from src.domains.tenants.models import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    Membership,
    Organization,
)
from src.domains.tenants.repository import TenantRepository

_ROLE_RANK = {ROLE_MEMBER: 0, ROLE_ADMIN: 1, ROLE_OWNER: 2}


class TenantService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = TenantRepository(db)

    async def list_organizations(self, user: AuthenticatedUser) -> list[Membership]:
        """List the user's organizations, creating the personal one on first call.

        Signup happens in the auth service (Better Auth), so the personal
        organization is created lazily on the first authenticated API call —
        same outcome as a signup hook, with no cross-service coupling.
        """
        memberships = await self._repo.list_memberships_for_user(user.user_id)
        if memberships:
            return memberships
        name = f"{user.name}'s workspace" if user.name else "Personal workspace"
        await self._repo.create_organization(name, owner_user_id=user.user_id)
        return await self._repo.list_memberships_for_user(user.user_id)

    async def create_organization(self, user: AuthenticatedUser, name: str) -> Membership:
        organization = await self._repo.create_organization(name, owner_user_id=user.user_id)
        membership = await self._repo.get_membership(organization.id, user.user_id)
        assert membership is not None  # noqa: S101 — just created above
        return membership

    async def rename_organization(
        self, user: AuthenticatedUser, organization_id: uuid.UUID, name: str
    ) -> Organization:
        membership = await self._require_membership(organization_id, user.user_id)
        self._require_rank(membership, ROLE_ADMIN)
        organization = membership.organization
        organization.name = name
        return organization

    async def list_members(
        self, user: AuthenticatedUser, organization_id: uuid.UUID
    ) -> tuple[list[Membership], dict[str, dict[str, str | None]]]:
        await self._require_membership(organization_id, user.user_id)
        members = await self._repo.list_members(organization_id)
        profiles = await self._repo.resolve_users([m.user_id for m in members])
        return members, profiles

    async def update_member_role(
        self,
        actor: AuthenticatedUser,
        organization_id: uuid.UUID,
        target_user_id: str,
        new_role: str,
    ) -> Membership:
        actor_membership = await self._require_membership(organization_id, actor.user_id)
        self._require_rank(actor_membership, ROLE_ADMIN)
        target = await self._repo.get_membership(organization_id, target_user_id)
        if target is None:
            raise NotFound("Member not found")

        actor_is_owner = actor_membership.role == ROLE_OWNER
        if target.role == ROLE_OWNER and not actor_is_owner:
            raise Forbidden("Only an owner can change another owner's role")
        if new_role == ROLE_OWNER and not actor_is_owner:
            raise Forbidden("Only an owner can grant the owner role")
        if target.role == ROLE_OWNER and new_role != ROLE_OWNER:
            await self._ensure_not_last_owner(organization_id, target_user_id)

        target.role = new_role
        return target

    async def remove_member(
        self,
        actor: AuthenticatedUser,
        organization_id: uuid.UUID,
        target_user_id: str,
    ) -> None:
        actor_membership = await self._require_membership(organization_id, actor.user_id)
        target = await self._repo.get_membership(organization_id, target_user_id)
        if target is None:
            raise NotFound("Member not found")

        is_self_removal = actor.user_id == target_user_id
        if not is_self_removal:
            self._require_rank(actor_membership, ROLE_ADMIN)
            if self._rank(target.role) >= self._rank(actor_membership.role):
                raise Forbidden("Cannot remove a member with an equal or higher role")
        if target.role == ROLE_OWNER:
            await self._ensure_not_last_owner(organization_id, target_user_id)

        await self._repo.delete_membership(target)

    async def _require_membership(self, organization_id: uuid.UUID, user_id: str) -> Membership:
        membership = await self._repo.get_membership(organization_id, user_id)
        if membership is None:
            # 404, not 403 — don't reveal that the organization exists.
            raise NotFound("Organization not found")
        return membership

    async def _ensure_not_last_owner(self, organization_id: uuid.UUID, user_id: str) -> None:
        members = await self._repo.list_members(organization_id)
        other_owners = [m for m in members if m.role == ROLE_OWNER and m.user_id != user_id]
        if not other_owners:
            raise Conflict("An organization must keep at least one owner")

    def _require_rank(self, membership: Membership, minimum_role: str) -> None:
        if self._rank(membership.role) < self._rank(minimum_role):
            raise Forbidden(f"Requires the {minimum_role} role")

    @staticmethod
    def _rank(role: str) -> int:
        return _ROLE_RANK.get(role, -1)
