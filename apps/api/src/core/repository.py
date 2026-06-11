import uuid
from typing import Any

from sqlalchemy import ForeignKey, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from src.core.tenancy import TenantContext


class TenantOwnedMixin:
    """Every tenant-owned table carries an indexed tenant_id."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


class TenantScopedRepository[ModelT: TenantOwnedMixin]:
    """Base repository that injects the tenant filter into every query.

    Domain code never writes `.where(tenant_id == ...)` by hand — it goes
    through `_query()` and `add()`, so forgetting the filter is impossible.
    Subclasses set `model` and build their queries on top of `_query()`.
    """

    model: type[ModelT]

    def __init__(self, db: AsyncSession, tenant: TenantContext) -> None:
        self._db = db
        self._tenant = tenant

    def _query(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.tenant_id == self._tenant.organization_id)

    async def get(self, entity_id: Any) -> ModelT | None:
        result = await self._db.execute(
            self._query().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[ModelT]:
        result = await self._db.execute(self._query())
        return list(result.scalars().all())

    def add(self, instance: ModelT) -> ModelT:
        # Forcibly stamp the active tenant — a forged tenant_id on the
        # instance is overwritten, never trusted.
        instance.tenant_id = self._tenant.organization_id
        self._db.add(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        if instance.tenant_id != self._tenant.organization_id:
            raise ValueError("Cannot delete an entity owned by another tenant")
        await self._db.delete(instance)
