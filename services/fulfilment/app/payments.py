"""Apply verified medication payment facts inside the consumer's inbox transaction."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Order, Quote


class PaymentEventRejected(Exception):
    """Safe error text only; rejected events remain retryable and may reach the DLQ."""


def confirm_payment(session, event, billing):
    if event.detail_type != "medication_payment_succeeded.v1":
        raise PaymentEventRejected("Unexpected payment event type")
    payment = billing.payment(event.data.payment_id)
    order = session.scalar(
        select(Order).where(Order.order_id == event.data.order_id).with_for_update()
    )
    if order is None:
        raise PaymentEventRejected("Payment order is unavailable")
    quote = session.get(Quote, order.quote_id) if order.quote_id is not None else None
    if (
        payment.payment_id != event.data.payment_id
        or payment.order_id != order.order_id
        or payment.tenant_id != order.tenant_id
        or payment.patient_id != order.patient_id
        or payment.quote_id != order.quote_id
        or payment.purpose != "medication_delivery"
        or payment.status != "succeeded"
        or payment.resolution != "none"
        or event.tenant_id != order.tenant_id
        or event.data.amount != payment.amount
        or payment.amount.currency != "SGD"
        or payment.amount.amount_minor != order.total_minor
        or order.payment_id != payment.payment_id
        or quote is None
        or quote.status != "accepted"
        or quote.order_id != order.order_id
        or quote.tenant_id != order.tenant_id
        or quote.total_minor != order.total_minor
        or quote.medication_subtotal_minor != order.medication_subtotal_minor
        or quote.delivery_fee_minor != order.delivery_fee_minor
    ):
        raise PaymentEventRejected("Payment context does not match reserved order")
    if order.payment_status == "succeeded":
        # A new event ID for the same payment must not regress a delivery in progress.
        return
    if order.status != "awaiting_payment" or order.payment_status != "pending":
        raise PaymentEventRejected("Order cannot accept payment without review")
    order.payment_status = "succeeded"
    order.status = "paid"
    order.updated_at = datetime.now(timezone.utc)
    # No commit here: the state change and M03 inbox entry must commit together.
