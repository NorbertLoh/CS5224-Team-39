"""Scoped service authentication to billing's authoritative payment API."""

import time
from uuid import UUID

import httpx
import jwt
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError
from telelink_common.events.payloads import Money

from app.payments import PaymentEventRejected


class PaymentFact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    payment_id: UUID
    order_id: UUID
    quote_id: UUID
    tenant_id: UUID
    patient_id: UUID
    purpose: str
    status: str
    amount: Money
    resolution: str
    updated_at: AwareDatetime | None = None


class BillingClient:
    def __init__(self, settings, *, transport=None):
        if not settings.billing_url or not settings.billing_secret:
            raise ValueError("Payment worker requires billing_url and billing_secret")
        self.url = settings.billing_url
        self.secret = settings.billing_secret
        self.client = httpx.Client(timeout=3, follow_redirects=False, transport=transport)

    def close(self):
        self.client.close()

    def payment(self, payment_id):
        return self.request("GET", f"/internal/payments/{payment_id}")

    def refund_required(self, payment_id, order_id, reason):
        return self.request(
            "POST",
            f"/internal/payments/{payment_id}/resolution",
            json={"resolution": "refund_required", "resource_id": str(order_id), "reason": reason},
        )

    def request(self, method, path, **kwargs):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "telelink-service:fulfilment",
                "sub": "fulfilment",
                "aud": "telelink-billing-fulfilment",
                "iat": now,
                "exp": now + 60,
            },
            self.secret.get_secret_value(),
            algorithm="HS256",
        )
        try:
            response = self.client.request(
                method,
                f"{self.url}{path}",
                headers={"Authorization": "Bearer " + token},
                **kwargs,
            )
            response.raise_for_status()
            return PaymentFact.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError):
            raise PaymentEventRejected("Billing payment verification unavailable") from None
