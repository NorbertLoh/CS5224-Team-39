"""Generate one private receipt per verified billing payment."""

from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select, text
from telelink_common.events.payloads import Money
from telelink_common.service_auth import service_token

from app.models import Document
from app.rendering.template_data import Receipt, ReceiptItem
from app.rendering.templates import render_receipt

PAYMENT_EVENTS = {
    "consultation_payment_succeeded.v1": ("consultation", "appointment_id"),
    "medication_payment_succeeded.v1": ("medication_delivery", "order_id"),
}


class PaidSnapshot(BaseModel):
    payment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    appointment_id: UUID
    order_id: UUID | None
    purpose: Literal["consultation", "medication_delivery"]
    paid_at: AwareDatetime
    clinic_name: str = Field(min_length=1, max_length=200)
    patient_name: str = Field(min_length=1, max_length=200)
    amount: Money
    delivery_fee_minor: int = Field(ge=0)


class GenerateReceipt:
    def __init__(self, settings, client, store):
        self.settings, self.client, self.store = settings, client, store

    def __call__(self, session, event):
        try:
            self.generate(session, event)
        except Exception:
            # Do not emit response bodies, names or billing details into worker logs.
            raise RuntimeError("Receipt PDF processing failed") from None

    def generate(self, session, event):
        purpose, reference = PAYMENT_EVENTS[event.detail_type]
        payment_id = event.data.payment_id
        document_id = uuid5(NAMESPACE_URL, f"telelink:receipt_pdf:{payment_id}")
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"document:receipt:{payment_id}"},
        )
        row = session.scalar(
            select(Document).where(
                Document.tenant_id == event.tenant_id,
                Document.kind == "receipt_pdf",
                Document.payment_id == payment_id,
            )
        )
        if row is not None:
            if row.status == "ready":
                return
            document_id = row.document_id
        if not self.settings.billing_url or not self.settings.billing_secret:
            raise ValueError("Receipt source is not configured")
        response = self.client.get(
            f"{self.settings.billing_url}/internal/payments/{payment_id}/receipt",
            headers={
                "Authorization": "Bearer "
                + service_token(
                    self.settings.billing_secret, "document", "telelink-billing-receipt"
                ),
                "X-Request-ID": str(event.correlation_id),
            },
        )
        if response.status_code != httpx.codes.OK:
            raise ValueError("Verified receipt snapshot unavailable")
        source = PaidSnapshot.model_validate(response.json())
        if (
            source.payment_id != payment_id
            or source.tenant_id != event.tenant_id
            or source.purpose != purpose
            or getattr(source, reference) != getattr(event.data, reference)
            or source.amount != event.data.amount
        ):
            raise ValueError("Receipt payment context mismatch")
        if row is not None and (row.appointment_id, row.patient_id) != (
            source.appointment_id,
            source.patient_id,
        ):
            raise ValueError("Receipt ownership mismatch")
        self.store.verify_private()
        key = f"receipts/{source.tenant_id}/{payment_id}.pdf"
        expected = {
            "document-id": str(document_id),
            "payment-id": str(payment_id),
            "tenant-id": str(source.tenant_id),
            "appointment-id": str(source.appointment_id),
        }
        stored = self.store.load(key, expected)
        if stored is None:
            total = source.amount.amount_minor
            items = [
                ReceiptItem(
                    description="Consultation" if purpose == "consultation" else "Medicines",
                    amount_minor=total - source.delivery_fee_minor,
                )
            ]
            if source.delivery_fee_minor:
                items.append(
                    ReceiptItem(description="Delivery", amount_minor=source.delivery_fee_minor)
                )
            receipt = Receipt(
                clinic_name=source.clinic_name,
                patient_name=source.patient_name,
                reference=str(document_id),
                payment_reference=str(payment_id),
                issued_at=source.paid_at,
                paid_at=source.paid_at,
                items=tuple(items),
                total_minor=total,
                currency=source.amount.currency,
            )
            stored = self.store.put(key, render_receipt(receipt), expected, source.patient_id, None)
        if stored.patient_id != source.patient_id or stored.doctor_id is not None:
            raise ValueError("Stored receipt ownership mismatch")
        if row is None:
            row = Document(
                document_id=document_id,
                tenant_id=source.tenant_id,
                appointment_id=source.appointment_id,
                patient_id=source.patient_id,
                payment_id=payment_id,
                kind="receipt_pdf",
            )
            session.add(row)
        row.status, row.storage_bucket, row.storage_key = "ready", self.store.bucket, key
        row.size_bytes, row.sha256 = stored.size_bytes, stored.sha256
