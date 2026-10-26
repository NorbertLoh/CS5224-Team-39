"""Authenticated provider snapshots commit with order state and the status outbox."""

from datetime import timedelta

from sqlalchemy import select

from app.api.deliveries import change_status, locked, utcnow
from app.delivery_orders import DeliveryUnavailable
from app.models import Delivery, Quote

ACTIVE = {"unknown", "submitted", "picked_up"}
PROGRESS = {"unknown": 0, "submitted": 1, "picked_up": 2, "delivered": 3}


def normalized(provider_status, current):
    if provider_status in {"ASSIGNING_DRIVER", "ON_GOING"}:
        return "submitted"
    if provider_status == "PICKED_UP":
        return "picked_up"
    if provider_status == "COMPLETED":
        return "delivered"
    if provider_status == "CANCELED":
        # A cancellation after pickup (or uncertain acceptance) is an exception,
        # rather than the submitted -> cancelled path allowed by C04.
        return "cancelled" if current == "submitted" else "failed"
    if provider_status in {"REJECTED", "EXPIRED"}:
        return "failed"
    raise DeliveryUnavailable("Unsupported provider delivery status")


def poll_delivery(sessions, delivery_id, provider, *, interval_seconds=60):
    if not 30 <= interval_seconds <= 3600:
        raise ValueError("Polling interval must be between 30 and 3600 seconds")
    with sessions.begin() as session:
        order, delivery = locked(session, delivery_id)
        if (
            delivery.status not in ACTIVE
            or not delivery.provider_order_id
            or delivery.next_poll_at > utcnow()
        ):
            return "skipped"
        try:
            quote = session.get(Quote, order.quote_id) if order.quote_id else None
            if (
                delivery.tenant_id != order.tenant_id
                or order.delivery_id != delivery_id
                or delivery.send_started_at is None
                or delivery.request_payload is None
                or quote is None
                or quote.order_id != order.order_id
                or quote.tenant_id != order.tenant_id
                or order.delivery_fee_minor is None
                or quote.delivery_fee_minor != order.delivery_fee_minor
            ):
                raise DeliveryUnavailable("Delivery tracking context mismatch")
            # Hold the same order/delivery locks through GET and commit. A second
            # poller rechecks next_poll_at after locking, so its stale selection is safe.
            result = provider.inspect(
                delivery.provider_order_id, delivery, quote, order.delivery_fee_minor
            )
            if result.orderId != delivery.provider_order_id:
                raise DeliveryUnavailable("Provider reference mismatch")
            target = normalized(result.status, delivery.status)
        except DeliveryUnavailable:
            delivery.poll_attempts = min(delivery.poll_attempts + 1, 20)
            delivery.poll_error = "provider_verification_unavailable"
            delivery.next_poll_at = utcnow() + timedelta(
                seconds=min(3600, interval_seconds * 2 ** min(delivery.poll_attempts, 6))
            )
            return "failed"
        delivery.last_polled_at = utcnow()
        delivery.next_poll_at = delivery.last_polled_at + timedelta(seconds=interval_seconds)
        delivery.poll_attempts = 0
        delivery.poll_error = None
        if target == delivery.status or (
            target in PROGRESS and PROGRESS[target] < PROGRESS[delivery.status]
        ):
            return "unchanged"
        change_status(session, delivery, target)
        if target == "delivered":
            order.status = "delivered"
            delivery.failure_code = None
        elif target in {"cancelled", "failed"}:
            order.status = "exception"
            delivery.failure_code = "provider_terminal_failure"
        else:
            order.status = "dispatched"
            delivery.failure_code = None
        order.updated_at = delivery.updated_at
        return "updated"


def poll_next(sessions, provider, *, interval_seconds=60):
    with sessions() as session:
        delivery_id = session.scalar(
            select(Delivery.delivery_id)
            .where(
                Delivery.status.in_(ACTIVE),
                Delivery.provider_order_id.is_not(None),
                Delivery.next_poll_at <= utcnow(),
            )
            .order_by(Delivery.next_poll_at, Delivery.created_at, Delivery.delivery_id)
            .limit(1)
        )
    if delivery_id is None:
        return "idle"
    return poll_delivery(sessions, delivery_id, provider, interval_seconds=interval_seconds)
