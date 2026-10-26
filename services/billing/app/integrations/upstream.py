import httpx
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.schemas import BillingProfile, MedicationReservation, Reservation


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
                "quote_expired",
                "quote_superseded",
                "prescription_not_issued",
                "medication_unavailable",
                "invalid_order_transition",
                "refund_appointment_active",
            }
            try:
                code = result.json()["error"]["code"]
            except (ValueError, KeyError, TypeError):
                code = "upstream_conflict"
            raise DomainError(
                409,
                code if code in allowed else "upstream_conflict",
                "Cancel the active appointment before requesting a refund."
                if code == "refund_appointment_active"
                else "Checkout cannot proceed.",
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

    def refund_action(self, payment, request_id, action):
        result = self.request(
            "POST",
            self.settings.scheduling_url,
            self.settings.scheduling_secret,
            "telelink-scheduling-billing",
            f"/internal/appointments/{payment.appointment_id}/{action}",
            request_id,
            json={
                "patient_id": str(payment.patient_id),
                "payment_id": str(payment.payment_id),
                "tenant_id": str(payment.tenant_id),
            },
        )
        try:
            value = result.json()
        except ValueError:
            raise DomainError(
                502, "upstream_error", "Invalid appointment refund context."
            ) from None
        if not isinstance(value, dict):
            raise DomainError(502, "upstream_error", "Invalid appointment refund context.")
        if any(
            value.get(field) != str(getattr(payment, field))
            for field in ("appointment_id", "patient_id", "tenant_id")
        ):
            raise DomainError(502, "upstream_error", "Invalid appointment refund context.")
        return value

    def prepare_refund(self, payment, request_id):
        return self.refund_action(payment, request_id, "refund-review")

    def complete_refund(self, payment, request_id):
        return self.refund_action(payment, request_id, "refund-complete")

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

    def reserve_medication(self, order_id, quote_id, patient_id, payment_id, request_id):
        result = self.request(
            "POST",
            self.settings.fulfilment_url,
            self.settings.fulfilment_secret,
            "telelink-fulfilment-billing",
            f"/internal/orders/{order_id}/checkout-reservation",
            request_id,
            json={
                "quote_id": str(quote_id),
                "patient_id": str(patient_id),
                "payment_id": str(payment_id),
            },
        )
        try:
            value = MedicationReservation.model_validate(result.json())
            if (value.order_id, value.quote_id, value.patient_id, value.payment_id) != (
                order_id,
                quote_id,
                patient_id,
                payment_id,
            ):
                raise ValueError("Context mismatch")
            return value
        except (ValueError, TypeError):
            raise DomainError(
                502, "upstream_error", "Invalid order reservation response."
            ) from None
