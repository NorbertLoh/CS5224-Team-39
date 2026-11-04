import hashlib

from sqlalchemy import text
from telelink_common.errors import DomainError

from app.access import can_read_items
from app.schemas import (
    Money,
    OrderOperational,
    OrderPublic,
)


def public_order(order, identity=None):
    fields = {
        key: getattr(order, key)
        for key in (
            "order_id",
            "tenant_id",
            "prescription_id",
            "appointment_id",
            "patient_id",
            "status",
            "medicine_status",
            "payment_status",
            "payment_id",
            "quote_id",
            "delivery_id",
            "created_at",
            "updated_at",
        )
    }
    result = OrderPublic(
        **fields,
        items=[
            dict(
                prescription_item_id=item.prescription_item_id,
                medication_id=item.medication_id,
                display_name=item.display_name,
                quantity=item.quantity,
                unit_price=Money(currency="SGD", amount_minor=item.unit_price_minor),
                line_total=Money(currency="SGD", amount_minor=item.line_total_minor),
            )
            for item in order.items
        ],
        medication_subtotal=Money(currency="SGD", amount_minor=order.medication_subtotal_minor),
        delivery_fee=None
        if order.delivery_fee_minor is None
        else Money(currency="SGD", amount_minor=order.delivery_fee_minor),
        total=None
        if order.total_minor is None
        else Money(currency="SGD", amount_minor=order.total_minor),
    )
    if identity is not None and not can_read_items(identity, order):
        return OrderOperational.model_validate(result.model_dump(exclude={"items"}))
    return result


def lock(session, scope):
    # Transaction-scoped locks cover absent rows as well as existing rows. All creators
    # lock subject/key then prescription, so retries cannot race unique constraints.
    lock_id = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def own_order(order, identity):
    if order.patient_id != identity.subject_id:
        raise DomainError(404, "not_found", "Resource not found.")
