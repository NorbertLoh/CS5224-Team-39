"""Only resource owners determine patient linkage; identity supplies current mailbox."""

from dataclasses import dataclass
from uuid import UUID

import httpx
from pydantic import BaseModel, StrictBool, ValidationError
from telelink_common.service_auth import service_token

from app.settings import validate_email


class RecipientLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Recipient:
    subject_id: UUID
    email: str


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
        }
        if event.detail_type not in routes:
            raise RecipientLookupError("Unsupported notification event")
        service, noun, key = routes[event.detail_type]
        resource_id = getattr(event.data, key)
        try:
            context = ResourceContext.model_validate(
                self.get(
                    service,
                    f"/internal/{noun}/{resource_id}/notification-context",
                    tenant_id=str(event.tenant_id),
                )
            )
            if context.resource_id != resource_id or context.tenant_id != event.tenant_id:
                raise ValueError("Context mismatch")
            if service == "document" and (
                context.appointment_id != event.data.appointment_id
                or context.prescription_id != event.data.prescription_id
                or context.medical_certificate_id != event.data.medical_certificate_id
            ):
                raise ValueError("Document context mismatch")
            if service == "fulfilment" and context.order_id != event.data.order_id:
                raise ValueError("Order context mismatch")
            if not context.eligible or (
                service == "fulfilment" and context.status != event.data.status
            ):
                return None  # Stale event; current owner state no longer warrants this email.
            mailbox = Mailbox.model_validate(
                self.get("identity", f"/internal/notification-recipients/{context.patient_id}")
            )
            if mailbox.recipient_id != context.patient_id:
                raise ValueError("Recipient mismatch")
            return Recipient(mailbox.recipient_id, validate_email(mailbox.email))
        except (ValidationError, ValueError):
            raise RecipientLookupError("Notification recipient context invalid") from None
