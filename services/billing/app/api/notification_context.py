"""Authoritative refund linkage for purpose-authenticated notification workers."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import Database
from app.models import Payment, RefundAttempt

router = APIRouter(tags=["internal"])


@router.get(
    "/internal/payments/{resource_id}/notification-context",
    dependencies=[
        Depends(
            require_service("notification", "telelink-billing-notification", "notification_secret")
        )
    ],
)
def refund_context(
    resource_id: UUID, tenant_id: UUID, refund_id: UUID, session: Database, response: Response
):
    payment = session.get(Payment, resource_id)
    refund = session.scalar(
        select(RefundAttempt).where(
            RefundAttempt.refund_id == refund_id, RefundAttempt.payment_id == resource_id
        )
    )
    if payment is None or payment.tenant_id != tenant_id or refund is None:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return {
        "resource_id": resource_id,
        "payment_id": resource_id,
        "refund_id": refund_id,
        "tenant_id": tenant_id,
        "patient_id": payment.patient_id,
        "appointment_id": payment.appointment_id,
        "order_id": payment.order_id,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "eligible": payment.status == "refunded" and refund.status == "succeeded",
    }
