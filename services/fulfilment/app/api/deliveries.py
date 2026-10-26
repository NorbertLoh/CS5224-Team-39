"""Durable, at-most-once submission intent and verified reference reconciliation."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select
from telelink_common.errors import DomainError, ErrorEnvelope
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.access import order_scope
from app.api.dependencies import DB, Identity
from app.delivery_orders import DeliveryUnavailable, SubmissionRejected, SubmissionUncertain
from app.models import Delivery, Order, Quote, event_outbox
from app.payments import PaymentEventRejected
from app.schemas import DeliveryPublic

router = APIRouter(
    tags=["deliveries"], responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 503)}
)


def utcnow():
    return datetime.now(timezone.utc)


def emit(session, delivery):
    add_event(
        session,
        event_outbox,
        new_event(
            "delivery_status_changed.v1",
            tenant_id=delivery.tenant_id,
            correlation_id=delivery.operation_id,
            occurred_at=delivery.updated_at,
            data={
                "delivery_id": delivery.delivery_id,
                "order_id": delivery.order_id,
                "status": delivery.status,
            },
        ),
    )


def change_status(session, delivery, status):
    if delivery.status != status:
        delivery.status = status
        delivery.updated_at = utcnow()
        emit(session, delivery)


def claim_deliveries(sessions, *, limit=10):
    with sessions.begin() as session:
        orders = session.scalars(
            select(Order)
            .where(
                Order.status == "paid",
                Order.payment_status == "succeeded",
                Order.medicine_status == "ready",
                Order.delivery_id.is_(None),
            )
            .order_by(Order.created_at, Order.order_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        ids = []
        for order in orders:
            delivery = Delivery(
                order_id=order.order_id,
                tenant_id=order.tenant_id,
                status="pending",
                updated_at=utcnow(),
            )
            session.add(delivery)
            session.flush()
            order.delivery_id = delivery.delivery_id
            order.status = "submitting"
            order.updated_at = delivery.updated_at
            emit(session, delivery)
            ids.append(delivery.delivery_id)
        return ids


def locked(session, delivery_id):
    # All writers lock order before delivery, matching readiness/payment writers.
    order_id = session.scalar(select(Delivery.order_id).where(Delivery.delivery_id == delivery_id))
    if order_id is None:
        raise DeliveryUnavailable("Delivery is unavailable")
    order = session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    delivery = session.scalar(
        select(Delivery).where(Delivery.delivery_id == delivery_id).with_for_update()
    )
    return order, delivery


def fail(session, order, delivery, reason, *, refund=False):
    delivery.failure_code = reason
    order.status = "exception"
    order.updated_at = utcnow()
    if refund:
        order.payment_status = "refund_required"
        delivery.resolution_reason = reason
    change_status(session, delivery, "failed")


def prepare_submission(sessions, delivery_id, provider, billing):
    with sessions.begin() as session:
        order, delivery = locked(session, delivery_id)
        if delivery.status != "pending" or delivery.send_started_at is not None:
            return None
        quote = session.get(Quote, order.quote_id) if order.quote_id else None
        if (
            order.status != "submitting"
            or order.payment_status != "succeeded"
            or order.medicine_status != "ready"
            or order.delivery_id != delivery_id
            or quote is None
            or quote.status != "accepted"
            or quote.order_id != order.order_id
            or quote.tenant_id != order.tenant_id
            or quote.total_minor != order.total_minor
            or quote.delivery_fee_minor != order.delivery_fee_minor
            or quote.medication_subtotal_minor != order.medication_subtotal_minor
        ):
            fail(session, order, delivery, "invalid_reservation")
            return None
        payment = billing.payment(order.payment_id)
        if (
            payment.payment_id != order.payment_id
            or payment.order_id != order.order_id
            or payment.quote_id != quote.quote_id
            or payment.patient_id != order.patient_id
            or payment.tenant_id != order.tenant_id
            or payment.purpose != "medication_delivery"
            or payment.status != "succeeded"
            or payment.resolution != "none"
            or payment.amount.currency != "SGD"
            or payment.amount.amount_minor != order.total_minor
            or payment.updated_at is None
        ):
            fail(session, order, delivery, "invalid_payment")
            return None
        if payment.updated_at >= quote.expires_at:
            fail(session, order, delivery, "quote_expired", refund=True)
            return None
        price, payload = provider.prepare(order, quote, delivery)
        if price.amount_minor != order.delivery_fee_minor:
            fail(session, order, delivery, "delivery_price_changed", refund=True)
            return None
        if price.expires_at <= utcnow():
            raise DeliveryUnavailable("Fresh delivery quotation expired")
        delivery.request_payload = payload
        delivery.provider_quote_expires_at = price.expires_at
        delivery.send_started_at = utcnow()
        # Commit an uncertain intent BEFORE POST: even a crash before sending cannot
        # cause an automatic resend when provider idempotency is not guaranteed.
        change_status(session, delivery, "unknown")
        session.flush()
        session.expunge(delivery)
        session.expunge(quote)
        return delivery, quote, order.delivery_fee_minor


def finish_submission(sessions, delivery_id, result, *, operator=None):
    with sessions.begin() as session:
        order, delivery = locked(session, delivery_id)
        if delivery.status != "unknown":
            if delivery.provider_order_id == result.orderId:
                return False
            raise DeliveryUnavailable("Delivery cannot accept a different provider reference")
        if delivery.provider_order_id not in {None, result.orderId}:
            raise DeliveryUnavailable("Provider reference conflicts with recorded attempt")
        delivery.provider_order_id = result.orderId
        if operator:
            delivery.reconciled_by = operator
            delivery.reconciled_at = utcnow()
        if result.status in {"CANCELED", "REJECTED", "EXPIRED"}:
            fail(session, order, delivery, "provider_terminal_failure")
        else:
            change_status(session, delivery, "submitted")
            order.status = "dispatched"
            order.updated_at = delivery.updated_at
        return True


def submit_delivery(sessions, delivery_id, provider, billing):
    prepared = prepare_submission(sessions, delivery_id, provider, billing)
    if prepared is None:
        return False
    delivery, quote, fee = prepared
    try:
        if delivery.provider_quote_expires_at <= utcnow():
            raise SubmissionRejected("Fresh quotation expired before submission")
        result = provider.submit(delivery, quote, fee)
    except SubmissionRejected:
        with sessions.begin() as session:
            order, current = locked(session, delivery_id)
            if current.status == "unknown":
                fail(session, order, current, "provider_rejected")
        return False
    except SubmissionUncertain as error:
        with sessions.begin() as session:
            _, current = locked(session, delivery_id)
            if current.status == "unknown":
                current.failure_code = "submission_uncertain"
                current.provider_order_id = error.provider_order_id
        return False
    return finish_submission(sessions, delivery_id, result)


def reconcile(sessions, delivery_id, provider_id, provider, operator):
    if not operator or len(operator) > 80:
        raise ValueError("A named operator (1-80 characters) is required")
    with sessions() as session:
        delivery = session.get(Delivery, delivery_id)
        if delivery is None or delivery.request_payload is None or delivery.send_started_at is None:
            raise DeliveryUnavailable("No sent delivery intent to reconcile")
        order = session.get(Order, delivery.order_id)
        quote = session.get(Quote, order.quote_id)
        # GET is safe to repeat. Only the independent verified provider response can
        # bind a portal-supplied reference; an operator cannot assert successful delivery.
        result = provider.inspect(provider_id, delivery, quote, order.delivery_fee_minor)
    return finish_submission(sessions, delivery_id, result, operator=operator)


def deliver_resolutions(sessions, billing):
    count = 0
    with sessions.begin() as session:
        ids = session.scalars(
            select(Delivery.order_id)
            .where(
                Delivery.resolution_reason.is_not(None),
                Delivery.resolution_delivered_at.is_(None),
            )
            .order_by(Delivery.created_at)
            .limit(10)
        ).all()
        for order_id in ids:
            order = session.scalar(
                select(Order).where(Order.order_id == order_id).with_for_update(skip_locked=True)
            )
            if order is None:
                continue
            delivery = session.scalar(
                select(Delivery).where(Delivery.order_id == order_id).with_for_update()
            )
            if delivery.resolution_delivered_at is not None:
                continue
            payment = billing.refund_required(
                order.payment_id, order.order_id, delivery.resolution_reason
            )
            if (
                payment.payment_id != order.payment_id
                or payment.order_id != order.order_id
                or payment.tenant_id != order.tenant_id
                or payment.patient_id != order.patient_id
                or payment.purpose != "medication_delivery"
                or payment.resolution != "refund_required"
                or payment.status not in {"succeeded", "refund_pending", "refund_failed"}
            ):
                raise PaymentEventRejected("Billing resolution acknowledgement invalid")
            delivery.resolution_delivered_at = utcnow()
            count += 1
    return count


@router.get("/deliveries/{delivery_id}", response_model=DeliveryPublic)
def get_delivery(delivery_id: UUID, identity: Identity, session: DB):
    delivery = session.scalar(
        select(Delivery)
        .join(Order, Delivery.order_id == Order.order_id)
        .where(
            Delivery.delivery_id == delivery_id,
            order_scope(identity),
        )
    )
    if delivery is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return DeliveryPublic.model_validate(delivery)
