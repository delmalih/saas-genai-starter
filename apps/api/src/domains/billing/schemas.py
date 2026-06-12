from pydantic import BaseModel


class BillingOut(BaseModel):
    enabled: bool
    plan: str
    subscription_status: str | None = None
    # Whether the caller's role can start checkout / open the portal.
    can_manage: bool = False


class CheckoutSessionOut(BaseModel):
    url: str


class PortalSessionOut(BaseModel):
    url: str
