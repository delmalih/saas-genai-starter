import hashlib
import hmac
import json
import time
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import get_settings
from src.domains.billing.service import BillingService
from src.domains.tenants.models import PLAN_FREE, PLAN_PRO, Membership, Organization
from src.llm.rate_limit import TenantRateLimiter

from tests.conftest import AuthHeaderFactory

WEBHOOK_SECRET = "whsec_test_secret"  # noqa: S105 — fake secret for tests


@pytest.fixture
async def org(db_session: AsyncSession) -> Organization:
    organization = Organization(name="Billing Co")
    organization.memberships = [
        Membership(user_id="alice", role="owner"),
        Membership(user_id="carol", role="member"),
    ]
    db_session.add(organization)
    await db_session.flush()
    return organization


@pytest.fixture
def owner_headers(org: Organization, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="alice"), "X-Org-Id": str(org.id)}


@pytest.fixture
def member_headers(org: Organization, auth_headers: AuthHeaderFactory) -> dict[str, str]:
    return {**auth_headers(user_id="carol"), "X-Org-Id": str(org.id)}


@pytest.fixture
def billing_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "billing_enabled", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_xxx")
    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "stripe_price_pro", "price_pro_123")


class FakeStripeClient:
    """Mimics the StripeClient surface the service touches."""

    def __init__(self) -> None:
        self.created_customers: list[dict[str, Any]] = []
        self.checkout_params: list[dict[str, Any]] = []
        self.portal_params: list[dict[str, Any]] = []
        self.customers = SimpleNamespace(create=self._create_customer)
        self.checkout = SimpleNamespace(
            sessions=SimpleNamespace(create=self._create_checkout_session)
        )
        self.billing_portal = SimpleNamespace(
            sessions=SimpleNamespace(create=self._create_portal_session)
        )

    def _create_customer(self, params: dict[str, Any]) -> Any:
        self.created_customers.append(params)
        return SimpleNamespace(id="cus_test_1")

    def _create_checkout_session(self, params: dict[str, Any]) -> Any:
        self.checkout_params.append(params)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    def _create_portal_session(self, params: dict[str, Any]) -> Any:
        self.portal_params.append(params)
        return SimpleNamespace(url="https://portal.stripe.test/session")


@pytest.fixture
def fake_stripe(monkeypatch: pytest.MonkeyPatch) -> FakeStripeClient:
    fake = FakeStripeClient()
    monkeypatch.setattr(BillingService, "_get_client", lambda self: fake)
    return fake


def sign_webhook(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Builds a real Stripe-Signature header so signature verification runs
    the genuine stripe code path."""
    timestamp = int(time.time())
    signed = hmac.new(
        secret.encode(), f"{timestamp}.{payload.decode()}".encode(), hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signed}"


def event_body(event_type: str, obj: dict[str, Any]) -> bytes:
    return json.dumps(
        {"id": f"evt_{uuid.uuid4().hex[:8]}", "type": event_type, "data": {"object": obj}}
    ).encode()


# --- Disabled by default ----------------------------------------------------


async def test_billing_disabled_reports_enabled_false(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await client.get("/billing", headers=owner_headers)
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "plan": "free",
        "subscription_status": None,
        "can_manage": True,
    }


async def test_billing_disabled_blocks_checkout_portal_and_webhook(
    client: httpx.AsyncClient, owner_headers: dict[str, str]
) -> None:
    assert (await client.post("/billing/checkout", headers=owner_headers)).status_code == 404
    assert (await client.post("/billing/portal", headers=owner_headers)).status_code == 404
    assert (await client.post("/webhooks/stripe", content=b"{}")).status_code == 404


# --- Checkout & portal -------------------------------------------------------


async def test_checkout_creates_customer_and_returns_url(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    billing_enabled: None,
    fake_stripe: FakeStripeClient,
    org: Organization,
) -> None:
    response = await client.post("/billing/checkout", headers=owner_headers)
    assert response.status_code == 200
    assert response.json() == {"url": "https://checkout.stripe.test/session"}

    assert fake_stripe.created_customers[0]["metadata"] == {"organization_id": str(org.id)}
    params = fake_stripe.checkout_params[0]
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_pro_123", "quantity": 1}]
    assert params["client_reference_id"] == str(org.id)
    assert org.stripe_customer_id == "cus_test_1"


async def test_checkout_reuses_existing_customer(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    billing_enabled: None,
    fake_stripe: FakeStripeClient,
    org: Organization,
) -> None:
    org.stripe_customer_id = "cus_existing"
    response = await client.post("/billing/checkout", headers=owner_headers)
    assert response.status_code == 200
    assert fake_stripe.created_customers == []
    assert fake_stripe.checkout_params[0]["customer"] == "cus_existing"


async def test_checkout_rejected_when_already_pro(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    billing_enabled: None,
    fake_stripe: FakeStripeClient,
    org: Organization,
) -> None:
    org.plan = PLAN_PRO
    response = await client.post("/billing/checkout", headers=owner_headers)
    assert response.status_code == 400


async def test_member_cannot_manage_billing(
    client: httpx.AsyncClient,
    member_headers: dict[str, str],
    billing_enabled: None,
    fake_stripe: FakeStripeClient,
) -> None:
    assert (await client.post("/billing/checkout", headers=member_headers)).status_code == 403
    assert (await client.post("/billing/portal", headers=member_headers)).status_code == 403
    billing = await client.get("/billing", headers=member_headers)
    assert billing.json()["can_manage"] is False


async def test_portal_requires_existing_customer(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    billing_enabled: None,
    fake_stripe: FakeStripeClient,
    org: Organization,
) -> None:
    assert (await client.post("/billing/portal", headers=owner_headers)).status_code == 400
    org.stripe_customer_id = "cus_existing"
    response = await client.post("/billing/portal", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["url"] == "https://portal.stripe.test/session"


# --- Webhook -----------------------------------------------------------------


async def test_webhook_rejects_bad_signature(
    client: httpx.AsyncClient, billing_enabled: None
) -> None:
    body = event_body("customer.subscription.updated", {})
    response = await client.post(
        "/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": sign_webhook(body, secret="whsec_wrong")},  # noqa: S106
    )
    assert response.status_code == 400
    assert (await client.post("/webhooks/stripe", content=body)).status_code == 400


async def test_subscribe_then_cancel_flow(
    client: httpx.AsyncClient,
    billing_enabled: None,
    org: Organization,
    db_session: AsyncSession,
) -> None:
    # Checkout completed → pro.
    body = event_body(
        "checkout.session.completed",
        {
            "client_reference_id": str(org.id),
            "customer": "cus_test_1",
            "subscription": "sub_test_1",
        },
    )
    response = await client.post(
        "/webhooks/stripe", content=body, headers={"Stripe-Signature": sign_webhook(body)}
    )
    assert response.status_code == 200
    await db_session.refresh(org)
    assert org.plan == PLAN_PRO
    assert org.stripe_customer_id == "cus_test_1"
    assert org.stripe_subscription_id == "sub_test_1"

    # Subscription deleted → back to free.
    body = event_body(
        "customer.subscription.deleted",
        {"id": "sub_test_1", "customer": "cus_test_1", "status": "canceled"},
    )
    response = await client.post(
        "/webhooks/stripe", content=body, headers={"Stripe-Signature": sign_webhook(body)}
    )
    assert response.status_code == 200
    await db_session.refresh(org)
    assert org.plan == PLAN_FREE
    assert org.subscription_status == "canceled"
    assert org.stripe_subscription_id is None


async def test_subscription_update_is_idempotent(
    client: httpx.AsyncClient,
    billing_enabled: None,
    org: Organization,
    db_session: AsyncSession,
) -> None:
    org.stripe_customer_id = "cus_test_1"
    await db_session.flush()
    body = event_body(
        "customer.subscription.updated",
        {"id": "sub_test_1", "customer": "cus_test_1", "status": "active"},
    )
    for _ in range(2):  # replayed delivery converges to the same state
        response = await client.post(
            "/webhooks/stripe", content=body, headers={"Stripe-Signature": sign_webhook(body)}
        )
        assert response.status_code == 200
    await db_session.refresh(org)
    assert org.plan == PLAN_PRO
    assert org.subscription_status == "active"


async def test_webhook_unknown_customer_is_acknowledged(
    client: httpx.AsyncClient, billing_enabled: None
) -> None:
    # Stripe retries on non-2xx — unknown orgs are logged, not errored.
    body = event_body(
        "customer.subscription.updated",
        {"id": "sub_x", "customer": "cus_unknown", "status": "active"},
    )
    response = await client.post(
        "/webhooks/stripe", content=body, headers={"Stripe-Signature": sign_webhook(body)}
    )
    assert response.status_code == 200


# --- Plan-based limits (SGS-061) ----------------------------------------------


def make_limiter() -> TenantRateLimiter:
    return TenantRateLimiter(
        client=None,  # type: ignore[arg-type]  # effective_limits never touches Redis
        requests_per_minute=30,
        tokens_per_day=500_000,
        plan_limits={"pro": (120, 5_000_000)},
    )


def test_pro_plan_raises_limits() -> None:
    assert make_limiter().effective_limits(plan=PLAN_PRO) == (120, 5_000_000)


def test_free_and_unknown_plans_use_base_limits() -> None:
    limiter = make_limiter()
    assert limiter.effective_limits(plan=PLAN_FREE) == (30, 500_000)
    assert limiter.effective_limits(plan="enterprise") == (30, 500_000)
    assert limiter.effective_limits() == (30, 500_000)


def test_admin_override_beats_plan() -> None:
    assert make_limiter().effective_limits(rpm_override=7, plan=PLAN_PRO) == (7, 5_000_000)


async def test_tenant_context_carries_plan(
    client: httpx.AsyncClient,
    owner_headers: dict[str, str],
    org: Organization,
    db_session: AsyncSession,
) -> None:
    org.plan = PLAN_PRO
    await db_session.flush()
    response = await client.get("/billing", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["plan"] == PLAN_PRO
