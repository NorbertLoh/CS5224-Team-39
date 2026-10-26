"""Authenticated billing read adapter; the real billing implementation remains B05."""

import time
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, ValidationError
from telelink_common.events.payloads import Money

from app.payments import PaymentEventRejected


class PaymentFact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    payment_id: UUID
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    purpose: str
    status: str
    amount: Money
    resolution: str = "none"


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

    def refund_required(self, recovery):
        payment = self.request(
            "POST",
            f"/internal/payments/{recovery.payment_id}/resolution",
            json={
                "resolution": "refund_required",
                "resource_id": str(recovery.appointment_id),
                "reason": recovery.reason,
            },
        )
        if (
            payment.payment_id != recovery.payment_id
            or payment.appointment_id != recovery.appointment_id
            or payment.tenant_id != recovery.tenant_id
            or payment.purpose != "consultation"
            or payment.status not in {"succeeded", "refund_pending", "refund_failed", "refunded"}
            or (payment.status != "refunded" and payment.resolution != "refund_required")
        ):
            raise PaymentEventRejected("Billing resolution acknowledgement invalid")
        return payment

    def request(self, method, path, **kwargs):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "telelink-service:scheduling",
                "sub": "scheduling",
                "aud": "telelink-billing-scheduling",
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
