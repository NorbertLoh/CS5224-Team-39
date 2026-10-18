import httpx
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.schemas import BillingProfile, Reservation


class CheckoutSources:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=3, trust_env=False, follow_redirects=False, transport=transport
        )

    def close(self):
        self.client.close()

    def request(self, method, base, secret, audience, path, request_id, **kwargs):
        if not base or not secret:
            raise DomainError(503, "unavailable", "Checkout source is not configured.")
        try:
            result = self.client.request(
                method,
                base + path,
                headers={
                    "Authorization": "Bearer " + service_token(secret, "billing", audience),
                    "X-Request-ID": request_id,
                },
                **kwargs,
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Checkout source is unavailable.") from None
        if result.status_code == 404:
            raise DomainError(404, "not_found", "Resource not found.")
        if result.status_code == 409:
            allowed = {
                "hold_expired",
                "already_paid",
                "clinic_not_active",
                "invalid_appointment_transition",
                "payment_attempt_pending",
            }
            try:
                code = result.json()["error"]["code"]
            except (ValueError, KeyError, TypeError):
                code = "upstream_conflict"
            raise DomainError(
                409, code if code in allowed else "upstream_conflict", "Checkout cannot proceed."
            )
        if result.status_code != 200:
            raise DomainError(503, "unavailable", "Checkout source is unavailable.")
        return result

    def reserve(self, appointment_id, patient_id, payment_id, request_id):
        result = self.request(
            "POST",
            self.settings.scheduling_url,
            self.settings.scheduling_secret,
            "telelink-scheduling-billing",
            f"/internal/appointments/{appointment_id}/checkout-reservation",
            request_id,
            json={"patient_id": str(patient_id), "payment_id": str(payment_id)},
        )
        try:
            value = Reservation.model_validate(result.json())
            if (value.appointment_id, value.patient_id, value.payment_id) != (
                appointment_id,
                patient_id,
                payment_id,
            ):
                raise ValueError("Context mismatch")
            return value
        except (ValueError, TypeError):
            raise DomainError(502, "upstream_error", "Invalid reservation response.") from None

    def profile(self, tenant_id, request_id):
        result = self.request(
            "GET",
            self.settings.tenant_url,
            self.settings.tenant_secret,
            "telelink-tenant-billing",
            f"/internal/clinics/{tenant_id}/billing-profile",
            request_id,
        )
        try:
            value = BillingProfile.model_validate(result.json())
            if value.tenant_id != tenant_id:
                raise ValueError("Context mismatch")
            return value
        except (ValueError, TypeError):
            raise DomainError(502, "upstream_error", "Invalid clinic response.") from None
