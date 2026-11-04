"""Minimal paid snapshot for the private receipt worker."""

from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, Request, Response
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import Database
from app.models import Payment, event_outbox
from app.schemas import Money

router = APIRouter(tags=["internal"])


class ReceiptSnapshot(BaseModel):
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


@router.get(
    "/internal/payments/{payment_id}/receipt",
    response_model=ReceiptSnapshot,
    dependencies=[
        Depends(require_service("document", "telelink-billing-receipt", "document_secret"))
    ],
)
def receipt_snapshot(payment_id: UUID, request: Request, response: Response, session: Database):
    payment = session.get(Payment, payment_id)
    event_id = uuid5(NAMESPACE_URL, f"telelink.billing:payment-success:{payment_id}")
    paid_at = session.scalar(
        select(event_outbox.c.event_time).where(event_outbox.c.event_id == event_id)
    )
    if payment is None or paid_at is None:
        raise DomainError(404, "not_found", "Verified payment not found.")
    sources = request.app.state.sources
    settings = request.app.state.settings
    request_id = request.state.request_id
    appointment_id = payment.appointment_id
    try:
        if payment.purpose == "medication_delivery":
            order = sources.request(
                "GET",
                settings.fulfilment_url,
                settings.fulfilment_secret,
                "telelink-fulfilment-billing",
                f"/internal/orders/{payment.order_id}/receipt-context",
                request_id,
            ).json()
            if any(
                order[key] != str(getattr(payment, key))
                for key in ("order_id", "tenant_id", "patient_id")
            ):
                raise ValueError("Order context mismatch")
            appointment_id = UUID(order["appointment_id"])
        clinic = sources.request(
            "GET",
            settings.tenant_url,
            settings.tenant_secret,
            "telelink-tenant-billing",
            f"/internal/clinics/{payment.tenant_id}/receipt-profile",
            request_id,
        ).json()
        patient = sources.request(
            "GET",
            settings.identity_url,
            settings.identity_secret,
            "telelink-identity-receipt",
            f"/internal/receipt-patients/{payment.patient_id}",
            request_id,
        ).json()
        if clinic["tenant_id"] != str(payment.tenant_id) or patient["patient_id"] != str(
            payment.patient_id
        ):
            raise ValueError("Receipt profile context mismatch")
        snapshot = ReceiptSnapshot(
            payment_id=payment.payment_id,
            tenant_id=payment.tenant_id,
            patient_id=payment.patient_id,
            appointment_id=appointment_id,
            order_id=payment.order_id,
            purpose=payment.purpose,
            paid_at=paid_at,
            clinic_name=clinic["clinic_name"],
            patient_name=patient["patient_name"],
            amount=Money(amount_minor=payment.amount_minor, currency=payment.currency),
            delivery_fee_minor=payment.delivery_fee_minor,
        )
    except (KeyError, TypeError, ValueError):
        raise DomainError(502, "upstream_error", "Invalid receipt context.") from None
    response.headers["Cache-Control"] = "no-store"
    return snapshot
