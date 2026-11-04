from datetime import datetime, timezone

from sqlalchemy import select
from telelink_common.errors import DomainError

from app.models import MAX_MONEY, CatalogueItem
from app.schemas import Money, QuotePublic
from app.services.pricing import saved_prices


def utcnow():
    return datetime.now(timezone.utc)


def public_quote(quote, now):
    return QuotePublic(
        contact_confirmed=bool(quote.destination.get("recipient_contact")),
        quote_id=quote.quote_id,
        order_id=quote.order_id,
        tenant_id=quote.tenant_id,
        status="expired" if quote.status == "active" and now >= quote.expires_at else quote.status,
        medication_subtotal=Money(amount_minor=quote.medication_subtotal_minor, currency="SGD"),
        delivery_fee=Money(amount_minor=quote.delivery_fee_minor, currency="SGD"),
        total=Money(amount_minor=quote.total_minor, currency="SGD"),
        expires_at=quote.expires_at,
        created_at=quote.created_at,
    )


def refresh_items(session, order):
    if order.pricing_mode == "prescription":
        prices = {
            row.prescription_item_id: row
            for row in saved_prices(session, order.tenant_id, order.prescription_id)
        }
        subtotal = 0
        for item in order.items:
            current = prices.get(item.prescription_item_id)
            if (
                current is None
                or current.medication_id != item.medication_id
                or current.quantity != item.quantity
            ):
                raise DomainError(
                    409, "medication_unpriced", "Clinic admin must price this prescription first."
                )
            item.unit_price_minor = current.unit_price_minor
            item.line_total_minor = item.quantity * current.unit_price_minor
            subtotal += item.line_total_minor
        if subtotal > MAX_MONEY:
            raise DomainError(409, "amount_out_of_range", "Order amount exceeds supported range.")
        return subtotal
    rows = session.scalars(
        select(CatalogueItem)
        .where(
            CatalogueItem.tenant_id == order.tenant_id,
            CatalogueItem.medication_id.in_([item.medication_id for item in order.items]),
        )
        .order_by(CatalogueItem.medication_id)
        .with_for_update()
    ).all()
    catalogue = {item.medication_id: item for item in rows}
    subtotal = 0
    for item in order.items:
        current = catalogue.get(item.medication_id)
        if current is None or not current.active:
            raise DomainError(409, "medication_unavailable", "Medication is unavailable.")
        if current.unit_price_minor is None:
            raise DomainError(
                409, "medication_unpriced", "Clinic admin must price all medicines first."
            )
        item.display_name = current.display_name
        item.unit_price_minor = current.unit_price_minor
        item.line_total_minor = current.unit_price_minor * item.quantity
        subtotal += item.line_total_minor
        if subtotal > MAX_MONEY:
            raise DomainError(409, "amount_out_of_range", "Order amount exceeds supported range.")
    return subtotal
