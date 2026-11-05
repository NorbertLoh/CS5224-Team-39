"""Only resource owners determine patient linkage; identity supplies current mailbox."""

from dataclasses import dataclass
from uuid import UUID

import httpx
from pydantic import BaseModel, StrictBool, ValidationError
from telelink_common.service_auth import service_token

from app.settings import validate_email


class RecipientLookupError(RuntimeError):
    pass


class NotificationDeferred(RuntimeError):
    """A clinical notice waits for consultation completion without spending send retries."""


@dataclass(frozen=True)
class Recipient:
    subject_id: UUID
    email: str
    context: object = None


class ResourceContext(BaseModel):
    resource_id: UUID
    tenant_id: UUID
    patient_id: UUID
    eligible: StrictBool
    appointment_id: UUID | None = None
    prescription_id: UUID | None = None
    medical_certificate_id: UUID | None = None
    order_id: UUID | None = None
    status: str | None = None
    payment_id: UUID | None = None
    refund_id: UUID | None = None
    kind: str | None = None
    clinic_name: str | None = None
    purpose: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    paid_at: str | None = None


class Mailbox(BaseModel):
    recipient_id: UUID
    email: str


class RecipientDirectory:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        for name in ("identity", "scheduling", "document", "fulfilment"):
            if not getattr(settings, name + "_url") or not getattr(settings, name + "_secret"):
                raise ValueError("All notification upstream URLs and credentials are required")
        self.client = httpx.Client(
            timeout=settings.lookup_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def get(self, service, path, **params):
        try:
            response = self.client.get(
                getattr(self.settings, service + "_url") + path,
                params=params,
                headers={
                    "Authorization": "Bearer "
                    + service_token(
                        getattr(self.settings, service + "_secret"),
                        "notification",
                        f"telelink-{service}-notification",
                    )
                },
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise RecipientLookupError("Notification recipient lookup unavailable") from None

    def resolve(self, event):
        routes = {
            "appointment_confirmed.v1": ("scheduling", "appointments", "appointment_id"),
            "document_ready.v1": ("document", "documents", "document_id"),
            "delivery_status_changed.v1": ("fulfilment", "deliveries", "delivery_id"),
            "appointment_cancelled.v1": ("scheduling", "appointments", "appointment_id"),
            "prescription_priced.v1": ("fulfilment", "prescriptions", "prescription_id"),
            "payment_refunded.v1": ("billing", "payments", "payment_id"),
        }
        if event.detail_type not in routes:
            raise RecipientLookupError("Unsupported notification event")
        service, noun, key = routes[event.detail_type]
        resource_id = getattr(event.data, key)
        params = {"tenant_id": str(event.tenant_id)}
        for field in ("patient_id", "refund_id"):
            if getattr(event.data, field, None) is not None:
                params[field] = str(getattr(event.data, field))
        try:
            context = ResourceContext.model_validate(
                self.get(
                    service,
                    f"/internal/{noun}/{resource_id}/notification-context",
                    **params,
                )
            )
            if context.resource_id != resource_id or context.tenant_id != event.tenant_id:
                raise ValueError("Context mismatch")
            if service == "document" and (
                context.appointment_id != event.data.appointment_id
                or context.prescription_id != event.data.prescription_id
                or context.medical_certificate_id != event.data.medical_certificate_id
                or context.payment_id != event.data.payment_id
            ):
                raise ValueError("Document context mismatch")
            if (
                event.detail_type == "delivery_status_changed.v1"
                and context.order_id != event.data.order_id
            ):
                raise ValueError("Order context mismatch")
            if event.detail_type == "prescription_priced.v1" and (
                context.prescription_id != event.data.prescription_id
                or context.patient_id != event.data.patient_id
            ):
                raise ValueError("Prescription context mismatch")
            if event.detail_type == "payment_refunded.v1" and (
                context.payment_id != event.data.payment_id
                or context.refund_id != event.data.refund_id
            ):
                raise ValueError("Refund context mismatch")
            if not context.eligible or (
                event.detail_type == "delivery_status_changed.v1"
                and context.status != event.data.status
            ):
                return None  # Stale event; current owner state no longer warrants this email.
            if event.detail_type == "appointment_confirmed.v1" and context.status == "cancelled":
                return None
            if event.detail_type == "appointment_cancelled.v1" and context.status != "cancelled":
                return None
            if (
                event.detail_type == "document_ready.v1"
                and event.data.payment_id
                and context.purpose == "consultation"
            ):
                appointment = ResourceContext.model_validate(
                    self.get(
                        "scheduling",
                        f"/internal/appointments/{event.data.appointment_id}/notification-context",
                        tenant_id=str(event.tenant_id),
                    )
                )
                if (appointment.resource_id, appointment.tenant_id, appointment.patient_id) != (
                    event.data.appointment_id,
                    event.tenant_id,
                    context.patient_id,
                ):
                    raise ValueError("Receipt appointment mismatch")
                context.starts_at = appointment.starts_at
            mailbox = Mailbox.model_validate(
                self.get("identity", f"/internal/notification-recipients/{context.patient_id}")
            )
            if mailbox.recipient_id != context.patient_id:
                raise ValueError("Recipient mismatch")
            return Recipient(mailbox.recipient_id, validate_email(mailbox.email), context)
        except (ValidationError, ValueError):
            raise RecipientLookupError("Notification recipient context invalid") from None

    def receipt(self, event, patient_id):
        # No signed URLs or arbitrary hosts: use only the authenticated owning service.
        try:
            with self.client.stream(
                "GET",
                self.settings.document_url
                + f"/internal/documents/{event.data.document_id}/notification-receipt",
                params={"tenant_id": str(event.tenant_id), "patient_id": str(patient_id)},
                headers={
                    "Authorization": "Bearer "
                    + service_token(
                        self.settings.document_secret,
                        "notification",
                        "telelink-document-notification",
                    )
                },
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-type") != "application/pdf":
                    raise ValueError("Expected receipt PDF")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 5_000_000:
                        raise ValueError("Receipt too large")
                if not data.startswith(b"%PDF-"):
                    raise ValueError("Invalid receipt PDF")
                return bytes(data)
        except (httpx.HTTPError, ValueError):
            raise RecipientLookupError("Receipt attachment unavailable") from None

    def clinical_ready(self, event, patient_id, appointment_id=None):
        appointment_id = appointment_id or event.data.appointment_id
        context = ResourceContext.model_validate(
            self.get(
                "scheduling",
                f"/internal/appointments/{appointment_id}/notification-context",
                tenant_id=str(event.tenant_id),
            )
        )
        if (context.resource_id, context.tenant_id, context.patient_id) != (
            appointment_id,
            event.tenant_id,
            patient_id,
        ):
            raise RecipientLookupError("Clinical appointment mismatch")
        if context.status in {"cancelled", "no_show", "expired"}:
            return False
        if context.status != "completed":
            raise NotificationDeferred("Consultation is not completed")
        return True
