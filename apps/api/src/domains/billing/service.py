import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.errors import ApiError, BadRequest, Forbidden
from src.core.tenancy import TenantContext
from src.domains.tenants.models import PLAN_FREE, PLAN_PRO, Organization

logger = structlog.get_logger(__name__)

# Subscription statuses that keep the org on the paid plan. past_due keeps
# access during the dunning window — Stripe sends `deleted` when it gives up.
ACTIVE_STATUSES = ("active", "trialing", "past_due")


class BillingMisconfigured(ApiError):
    def __init__(self) -> None:
        super().__init__(
            503,
            "billing_misconfigured",
            "Billing is enabled but Stripe is not fully configured",
        )


class BillingService:
    """Stripe checkout/portal sessions and webhook-driven state sync.

    Stripe is imported lazily so the module stays inert (and the dependency
    optional at runtime) when BILLING_ENABLED is off.
    """

    def __init__(self, db: AsyncSession, stripe_client: Any | None = None):
        self._db = db
        self._client = stripe_client

    def _get_client(self) -> Any:
        if self._client is None:
            import stripe

            settings = get_settings()
            if not settings.stripe_secret_key:
                raise BillingMisconfigured()
            self._client = stripe.StripeClient(settings.stripe_secret_key)
        return self._client

    @staticmethod
    def require_manager(tenant: TenantContext) -> None:
        if tenant.role not in ("owner", "admin"):
            raise Forbidden("Only owners and admins can manage billing")

    async def _get_organization(self, organization_id: uuid.UUID) -> Organization:
        org = await self._db.get(Organization, organization_id)
        if org is None:  # pragma: no cover - tenant context already verified it
            raise BadRequest("Unknown organization")
        return org

    async def create_checkout_session(self, tenant: TenantContext) -> str:
        settings = get_settings()
        if not settings.stripe_price_pro:
            raise BillingMisconfigured()
        org = await self._get_organization(tenant.organization_id)
        if org.plan == PLAN_PRO:
            raise BadRequest("Organization is already on the Pro plan")

        client = self._get_client()
        if org.stripe_customer_id is None:
            customer = await asyncio.to_thread(
                client.customers.create,
                params={
                    "name": org.name,
                    "metadata": {"organization_id": str(org.id)},
                },
            )
            org.stripe_customer_id = customer.id

        session = await asyncio.to_thread(
            client.checkout.sessions.create,
            params={
                "mode": "subscription",
                "customer": org.stripe_customer_id,
                "line_items": [{"price": settings.stripe_price_pro, "quantity": 1}],
                "client_reference_id": str(org.id),
                "success_url": f"{settings.web_base_url}/settings?billing=success",
                "cancel_url": f"{settings.web_base_url}/settings?billing=canceled",
            },
        )
        return str(session.url)

    async def create_portal_session(self, tenant: TenantContext) -> str:
        settings = get_settings()
        org = await self._get_organization(tenant.organization_id)
        if org.stripe_customer_id is None:
            raise BadRequest("No billing account yet — upgrade first")
        session = await asyncio.to_thread(
            self._get_client().billing_portal.sessions.create,
            params={
                "customer": org.stripe_customer_id,
                "return_url": f"{settings.web_base_url}/settings",
            },
        )
        return str(session.url)

    # --- Webhook ------------------------------------------------------------

    @staticmethod
    def verify_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
        """Returns the verified event as a plain dict or raises BadRequest."""
        import json

        import stripe

        settings = get_settings()
        if not settings.stripe_webhook_secret:
            raise BillingMisconfigured()
        if not signature:
            raise BadRequest("Missing Stripe-Signature header")
        try:
            stripe.WebhookSignature.verify_header(  # type: ignore[no-untyped-call]
                payload.decode("utf-8"), signature, settings.stripe_webhook_secret
            )
            event = json.loads(payload)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise BadRequest("Invalid Stripe webhook signature") from exc
        if not isinstance(event, dict):
            raise BadRequest("Malformed Stripe event payload")
        return event

    async def handle_event(self, event: dict[str, Any]) -> None:
        """Sync subscription state from the event object. Handlers write the
        full target state (not a delta), so replayed or out-of-order webhook
        deliveries converge instead of corrupting."""
        event_type = event.get("type", "")
        obj = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            org = await self._org_for_checkout(obj)
            if org is None:
                logger.warning("billing.webhook_org_not_found", event_type=event_type)
                return
            org.stripe_customer_id = obj.get("customer") or org.stripe_customer_id
            org.stripe_subscription_id = obj.get("subscription")
            org.subscription_status = "active"
            org.plan = PLAN_PRO
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            org = await self._org_for_customer(obj.get("customer"))
            if org is None:
                logger.warning("billing.webhook_org_not_found", event_type=event_type)
                return
            status = "canceled" if event_type.endswith("deleted") else obj.get("status")
            org.subscription_status = status
            org.plan = PLAN_PRO if status in ACTIVE_STATUSES else PLAN_FREE
            org.stripe_subscription_id = None if org.plan == PLAN_FREE else obj.get("id")
        else:
            logger.debug("billing.webhook_ignored", event_type=event_type)
            return
        logger.info(
            "billing.webhook_applied",
            event_type=event_type,
            organization_id=str(org.id),
            plan=org.plan,
        )

    async def _org_for_checkout(self, obj: dict[str, Any]) -> Organization | None:
        reference = obj.get("client_reference_id")
        if reference:
            try:
                return await self._db.get(Organization, uuid.UUID(reference))
            except ValueError:
                return None
        return await self._org_for_customer(obj.get("customer"))

    async def _org_for_customer(self, customer_id: str | None) -> Organization | None:
        if not customer_id:
            return None
        result = await self._db.execute(
            select(Organization).where(Organization.stripe_customer_id == customer_id)
        )
        return result.scalar_one_or_none()
