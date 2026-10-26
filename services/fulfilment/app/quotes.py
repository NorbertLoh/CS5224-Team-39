import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import can_read_items
from app.catalogue import DB, Identity
from app.models import MAX_MONEY, CatalogueItem, Order, Quote, QuoteRequest
from app.orders import IdempotencyKey, Patient, lock, own_order
from app.prescription_prices import saved_prices
from app.schemas import DeliveryDetails, Destination, Money, QuoteCreate, QuotePublic

router = APIRouter(
    tags=["quotes"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)},
)


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


@router.post(
    "/orders/{order_id}/quotes",
    response_model=QuotePublic,
    status_code=201,
    responses={200: {"model": QuotePublic}},
)
def create_quote(
    order_id: UUID,
    body: QuoteCreate,
    request: Request,
    response: Response,
    identity: Patient,
    session: DB,
    idempotency_key: IdempotencyKey,
):
    fingerprint = hashlib.sha256(
        json.dumps(
            {"order_id": str(order_id), **body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    lock(session, f"quotes:key:{identity.subject_id}:{idempotency_key}")
    previous = session.get(QuoteRequest, (identity.subject_id, idempotency_key))
    if previous is not None:
        if previous.fingerprint != fingerprint:
            raise DomainError(409, "idempotency_conflict", "Key was used for a different request.")
        quote = session.get(Quote, previous.quote_id)
        own_order(session.get(Order, quote.order_id), identity)
        response.status_code = 200
        # C03 replay preserves the original response, including its original deadline.
        return QuotePublic.model_validate(previous.response_payload)
    order = session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    if order is None:
        raise DomainError(404, "not_found", "Resource not found.")
    own_order(order, identity)
    if order.payment_status == "pending":
        from app.checkout import release_failed

        release_failed(session, order, request.app.state.settings)
    if (
        order.payment_status in {"succeeded", "refund_required", "refunded"}
        or order.status == "paid"
    ):
        raise DomainError(409, "already_paid", "Order has already been paid.")
    if order.payment_status != "unpaid" or order.payment_id is not None:
        raise DomainError(409, "payment_pending", "Payment must be reconciled before re-quoting.")
    if order.status != "awaiting_payment":
        raise DomainError(409, "order_not_quotable", "Order cannot be quoted.")
    if order.quote_id is not None:
        previous_quote = session.get(Quote, order.quote_id)
        if previous_quote is not None and previous_quote.status == "accepted":
            raise DomainError(409, "payment_pending", "Accepted quote cannot be replaced.")
    subtotal = refresh_items(session, order)
    # Bounded provider I/O while holding order/catalogue locks serializes repricing
    # and future checkout reservation. Quote creation never submits a delivery.
    if request.app.state.settings.tenant_url:
        origin = request.app.state.clinic_locations.get(order.tenant_id)
        price = request.app.state.delivery_quotes.quote(
            order.tenant_id, body.destination, origin=origin
        )
    else:
        price = request.app.state.delivery_quotes.quote(order.tenant_id, body.destination)
    now = utcnow()
    expires_at = min(price.expires_at, now + timedelta(minutes=10))
    if expires_at <= now:
        raise DomainError(409, "quote_expired", "Provider quotation has expired.")
    total = subtotal + price.amount_minor
    if total > MAX_MONEY:
        raise DomainError(409, "amount_out_of_range", "Order amount exceeds supported range.")
    for old in session.scalars(
        select(Quote).where(Quote.order_id == order_id, Quote.status == "active")
    ).all():
        old.status = "expired" if now >= old.expires_at else "superseded"
    session.flush()  # release the partial unique index before inserting replacement
    quote = Quote(
        order_id=order_id,
        tenant_id=order.tenant_id,
        medication_subtotal_minor=subtotal,
        delivery_fee_minor=price.amount_minor,
        total_minor=total,
        created_at=now,
        expires_at=expires_at,
        destination={
            **body.destination.model_dump(mode="json"),
            "recipient_contact": body.recipient.model_dump(mode="json"),
        },
        provider_context=price.context,
        items=[
            dict(
                prescription_item_id=str(item.prescription_item_id),
                medication_id=str(item.medication_id),
                display_name=item.display_name,
                quantity=item.quantity,
                unit_price_minor=item.unit_price_minor,
                line_total_minor=item.line_total_minor,
            )
            for item in order.items
        ],
    )
    session.add(quote)
    session.flush()
    order.quote_id = quote.quote_id
    order.medication_subtotal_minor = subtotal
    order.delivery_fee_minor = price.amount_minor
    order.total_minor = total
    order.updated_at = now
    result = public_quote(quote, now)
    session.add(
        QuoteRequest(
            subject_id=identity.subject_id,
            key=idempotency_key,
            fingerprint=fingerprint,
            quote_id=quote.quote_id,
            response_payload=result.model_dump(mode="json"),
        )
    )
    session.commit()
    return result


@router.get("/quotes/{quote_id}", response_model=QuotePublic)
def get_quote(quote_id: UUID, identity: Identity, session: DB):
    quote = session.get(Quote, quote_id)
    if quote is None or not can_read_items(identity, session.get(Order, quote.order_id)):
        raise DomainError(404, "not_found", "Resource not found.")
    return public_quote(quote, utcnow())


@router.get("/orders/{order_id}/delivery-details", response_model=DeliveryDetails)
def delivery_details(order_id: UUID, response: Response, identity: Patient, session: DB):
    order = session.get(Order, order_id)
    if order is None:
        raise DomainError(404, "not_found", "Resource not found.")
    own_order(order, identity)
    response.headers["Cache-Control"] = "no-store"
    quote = session.get(Quote, order.quote_id) if order.quote_id else None
    if quote is None:
        return DeliveryDetails()
    return DeliveryDetails(
        quote_id=quote.quote_id,
        destination=Destination.model_validate(
            {key: quote.destination[key] for key in ("address_line", "postal_code", "country_code")}
        ),
        recipient=quote.destination.get("recipient_contact"),
    )
