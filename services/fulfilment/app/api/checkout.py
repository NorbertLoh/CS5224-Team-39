"""Atomic C04 reservation of an immutable quote by the billing service."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import DB, Patient
from app.api.orders import own_order, public_order
from app.billing import BillingClient
from app.models import Order, Quote
from app.schemas import MedicineReady, OrderPublic, StrictModel

router = APIRouter(tags=["internal"])
billing = require_service("billing", "telelink-fulfilment-billing", "billing_secret")


class ReservationCreate(StrictModel):
    quote_id: UUID
    patient_id: UUID
    payment_id: UUID


def release_failed(session, order, settings):
    """Only billing's terminal operation fact can release an accepted attempt."""
    if order.payment_status != "pending" or order.payment_id is None:
        return
    if not settings.billing_url or not settings.billing_secret:
        raise DomainError(503, "unavailable", "Payment verification is not configured.")
    client = BillingClient(settings)
    try:
        fact = client.checkout_attempt(order.payment_id)
    finally:
        client.close()
    expected = {
        "payment_id": str(order.payment_id),
        "order_id": str(order.order_id),
        "patient_id": str(order.patient_id),
        "quote_id": str(order.quote_id),
    }
    if any(fact.get(key) != value for key, value in expected.items()):
        raise DomainError(502, "upstream_error", "Invalid payment context.")
    if fact.get("status") != "failed":
        raise DomainError(409, "payment_attempt_pending", "Existing payment needs reconciliation.")
    quote = session.get(Quote, order.quote_id)
    quote.status = "expired" if datetime.now(timezone.utc) >= quote.expires_at else "active"
    order.payment_id = None
    order.payment_status = "unpaid"
    order.updated_at = datetime.now(timezone.utc)
    session.flush()


@router.post("/orders/{order_id}/reconcile-payment", response_model=OrderPublic)
def reconcile_payment(
    order_id: UUID,
    request: Request,
    identity: Patient,
    session: DB,
    body: MedicineReady | None = None,
):
    order = session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    if order is None:
        raise DomainError(404, "not_found", "Resource not found.")
    own_order(order, identity)
    release_failed(session, order, request.app.state.settings)
    result = public_order(order)
    session.commit()
    return result


@router.post("/internal/orders/{order_id}/checkout-reservation")
def reserve(
    order_id: UUID,
    body: ReservationCreate,
    request: Request,
    caller: Annotated[str, Depends(billing)],
    session: DB,
):
    order = session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    if order is None or order.patient_id != body.patient_id:
        raise DomainError(404, "not_found", "Resource not found.")
    if order.payment_status == "pending" and order.payment_id != body.payment_id:
        release_failed(session, order, request.app.state.settings)
    if order.status != "awaiting_payment" or order.payment_status not in {"unpaid", "pending"}:
        raise DomainError(409, "already_paid", "Order cannot start another checkout.")
    quote = session.get(Quote, body.quote_id)
    if quote is None or quote.order_id != order_id or quote.tenant_id != order.tenant_id:
        raise DomainError(404, "not_found", "Resource not found.")
    replay = order.payment_id == body.payment_id and order.quote_id == body.quote_id
    if not replay and not quote.destination.get("recipient_contact"):
        raise DomainError(
            409, "delivery_contact_required", "Confirm delivery contact details before payment."
        )
    if order.payment_id is not None and not replay:
        raise DomainError(409, "payment_attempt_pending", "Order has a pending checkout.")
    if order.quote_id != body.quote_id or quote.status not in {"active", "accepted"}:
        raise DomainError(409, "quote_superseded", "The quote is no longer active.")
    if not replay and (quote.status != "active" or datetime.now(timezone.utc) >= quote.expires_at):
        raise DomainError(409, "quote_expired", "The delivery quote has expired.")
    context = request.app.state.dispensing.get(
        order.prescription_id, order.patient_id, request.state.request_id
    )
    if any(
        getattr(context, key) != getattr(order, key)
        for key in ("prescription_id", "patient_id", "tenant_id", "appointment_id")
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    if context.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
    source = {
        (str(item.prescription_item_id), str(item.medication_id), item.quantity)
        for item in context.items
    }
    snapshot = {
        (item["prescription_item_id"], item["medication_id"], item["quantity"])
        for item in quote.items
    }
    if source != snapshot:
        raise DomainError(409, "prescription_not_issued", "Dispensing context changed.")
    if not replay and datetime.now(timezone.utc) >= quote.expires_at:
        raise DomainError(409, "quote_expired", "The delivery quote has expired.")
    order.payment_id = body.payment_id
    order.payment_status = "pending"
    quote.status = "accepted"
    if not replay:
        order.updated_at = datetime.now(timezone.utc)
    result = public_order(order).model_dump(mode="json")
    result.update(quote_status="accepted", expires_at=quote.expires_at.isoformat())
    # Match B06's minimum projection; no addresses or clinical instructions.
    result["items"] = [
        {
            "prescription_item_id": item["prescription_item_id"],
            "medication_id": item["medication_id"],
            "quantity": item["quantity"],
            "unit_price": {"amount_minor": item["unit_price_minor"], "currency": "SGD"},
            "line_total": {"amount_minor": item["line_total_minor"], "currency": "SGD"},
        }
        for item in quote.items
    ]
    session.commit()
    return {
        key: result[key]
        for key in (
            "order_id",
            "quote_id",
            "tenant_id",
            "patient_id",
            "payment_id",
            "status",
            "payment_status",
            "quote_status",
            "items",
            "medication_subtotal",
            "delivery_fee",
            "total",
            "expires_at",
        )
    }
