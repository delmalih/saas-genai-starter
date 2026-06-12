from typing import Annotated

from fastapi import APIRouter, Header, Request

from src.core.config import get_settings
from src.core.db import DbSession
from src.core.errors import NotFound
from src.core.tenancy import CurrentTenant
from src.domains.billing.schemas import BillingOut, CheckoutSessionOut, PortalSessionOut
from src.domains.billing.service import BillingService
from src.domains.tenants.models import Organization

router = APIRouter(prefix="/billing", tags=["billing"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["billing"])


def _require_enabled() -> None:
    if not get_settings().billing_enabled:
        raise NotFound("Billing is not enabled")


@router.get("")
async def get_billing(tenant: CurrentTenant, db: DbSession) -> BillingOut:
    """Always available — the web app uses `enabled` to show or hide billing UI."""
    org = await db.get(Organization, tenant.organization_id)
    if org is None:  # pragma: no cover - tenant context already verified membership
        raise NotFound("Organization not found")
    return BillingOut(
        enabled=get_settings().billing_enabled,
        plan=org.plan,
        subscription_status=org.subscription_status,
        can_manage=tenant.role in ("owner", "admin"),
    )


@router.post("/checkout")
async def create_checkout_session(tenant: CurrentTenant, db: DbSession) -> CheckoutSessionOut:
    _require_enabled()
    BillingService.require_manager(tenant)
    service = BillingService(db)
    url = await service.create_checkout_session(tenant)
    await db.commit()  # persist a customer id created on the way
    return CheckoutSessionOut(url=url)


@router.post("/portal")
async def create_portal_session(tenant: CurrentTenant, db: DbSession) -> PortalSessionOut:
    _require_enabled()
    BillingService.require_manager(tenant)
    url = await BillingService(db).create_portal_session(tenant)
    return PortalSessionOut(url=url)


@webhooks_router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    _require_enabled()
    payload = await request.body()
    event = BillingService.verify_webhook(payload, stripe_signature)
    await BillingService(db).handle_event(event)
    await db.commit()
    return {"received": True}
