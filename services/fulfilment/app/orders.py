import hashlib
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select, text, tuple_
from telelink_common.access import CurrentIdentity, require_global_role
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import can_read_items, order_scope, permission_fingerprint, require_clinic
from app.catalogue import DB, Identity
from app.models import CatalogueItem, Order, OrderItem, OrderRequest
from app.pagination import decode, encode
from app.schemas import (
    MAX_MONEY,
    MedicineReady,
    Money,
    OrderCreate,
    OrderOperational,
    OrderPage,
    OrderPublic,
    OrderStatus,
)

router = APIRouter(
    tags=["orders"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 502, 503)},
)
Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._-]{1,64}$")]


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


@router.post(
    "/orders", response_model=OrderPublic, status_code=201, responses={200: {"model": OrderPublic}}
)
def create_order(
    body: OrderCreate,
    request: Request,
    response: Response,
    identity: Patient,
    session: DB,
    idempotency_key: IdempotencyKey,
):
    lock(session, f"orders:key:{identity.subject_id}:{idempotency_key}")
    previous = session.get(OrderRequest, (identity.subject_id, idempotency_key))
    if previous is not None:
        if previous.prescription_id != body.prescription_id:
            raise DomainError(409, "idempotency_conflict", "Key was used for a different request.")
        own_order(session.get(Order, previous.order_id), identity)
        response.status_code = 200
        return OrderPublic.model_validate(previous.response_payload)
    lock(session, f"orders:prescription:{body.prescription_id}")
    order = session.scalar(select(Order).where(Order.prescription_id == body.prescription_id))
    if order is not None:
        own_order(order, identity)
        response.status_code = 200
    else:
        # Upstream source is explicitly supplied; default fails closed. Never trust
        # IDs, quantities, names or prices from the browser except prescription selection.
        context = request.app.state.dispensing.get(
            body.prescription_id, identity.subject_id, request.state.request_id
        )
        if (
            context.prescription_id != body.prescription_id
            or context.patient_id != identity.subject_id
        ):
            raise DomainError(404, "not_found", "Resource not found.")
        if context.status != "issued":
            raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
        rows = session.scalars(
            select(CatalogueItem)
            .where(
                CatalogueItem.tenant_id == context.tenant_id,
                CatalogueItem.medication_id.in_([item.medication_id for item in context.items]),
            )
            .order_by(CatalogueItem.medication_id)
            .with_for_update()
        ).all()
        catalogue = {item.medication_id: item for item in rows}
        items = []
        subtotal = 0
        for position, source in enumerate(context.items):
            item = catalogue.get(source.medication_id)
            if item is None or not item.active:
                raise DomainError(409, "medication_unavailable", "Medication is unavailable.")
            line_total = source.quantity * item.unit_price_minor
            subtotal += line_total
            if subtotal > MAX_MONEY:
                raise DomainError(
                    409, "amount_out_of_range", "Order amount exceeds supported range."
                )
            items.append(
                OrderItem(
                    prescription_item_id=source.prescription_item_id,
                    medication_id=source.medication_id,
                    position=position,
                    display_name=item.display_name,
                    quantity=source.quantity,
                    unit_price_minor=item.unit_price_minor,
                    line_total_minor=line_total,
                )
            )
        order = Order(
            tenant_id=context.tenant_id,
            patient_id=context.patient_id,
            appointment_id=context.appointment_id,
            prescription_id=context.prescription_id,
            medication_subtotal_minor=subtotal,
            items=items,
        )
        session.add(order)
        session.flush()
    result = public_order(order)
    session.add(
        OrderRequest(
            subject_id=identity.subject_id,
            key=idempotency_key,
            prescription_id=body.prescription_id,
            order_id=order.order_id,
            response_payload=result.model_dump(mode="json"),
        )
    )
    session.commit()
    return result


@router.get("/orders/{order_id}", response_model=OrderPublic | OrderOperational)
def get_order(order_id: UUID, identity: Identity, session: DB):
    order = session.scalar(select(Order).where(Order.order_id == order_id, order_scope(identity)))
    if order is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return public_order(order, identity)


@router.post("/orders/{order_id}/ready", response_model=OrderPublic)
def mark_medicine_ready(
    order_id: UUID,
    request: Request,
    identity: Identity,
    session: DB,
    body: MedicineReady | None = None,
):
    # Share the order row lock with quotes and future payment/delivery writers.
    order = session.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
    if order is None:
        raise DomainError(404, "not_found", "Resource not found.")
    require_clinic(identity, order.tenant_id, {"clinic_admin"})
    if order.status not in {"awaiting_payment", "paid"} or order.payment_status in {
        "refund_required",
        "refunded",
    }:
        raise DomainError(409, "order_not_active", "Order cannot be marked medicine-ready.")
    context = request.app.state.dispensing.get(
        order.prescription_id, order.patient_id, request.state.request_id
    )
    if any(
        getattr(context, field) != getattr(order, field)
        for field in ("prescription_id", "tenant_id", "patient_id", "appointment_id")
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    if context.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
    if order.medicine_status != "ready":
        order.medicine_status = "ready"
        order.updated_at = datetime.now(timezone.utc)
    result = public_order(order)
    session.commit()
    return result


@router.get("/orders", response_model=OrderPage)
def list_orders(
    request: Request,
    identity: Identity,
    session: DB,
    tenant_id: UUID | None = None,
    status: OrderStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    sort: Literal["oldest", "newest"] = "oldest",
):
    query = select(Order).where(order_scope(identity))
    if tenant_id is not None:
        query = query.where(Order.tenant_id == tenant_id)
    if status is not None:
        query = query.where(Order.status == status)
    scope = ["orders", str(tenant_id), status, permission_fingerprint(identity), limit]
    if sort == "newest":
        scope.append("newest")
    if cursor:
        created_at, resource_id = decode(request.app.state.settings, scope, cursor, timestamp=True)
        position = tuple_(Order.created_at, Order.order_id)
        query = query.where(
            position < tuple_(created_at, resource_id)
            if sort == "newest" else position > tuple_(created_at, resource_id)
        )
    ordering = (
        (Order.created_at.desc(), Order.order_id.desc())
        if sort == "newest" else (Order.created_at, Order.order_id)
    )
    rows = session.scalars(query.order_by(*ordering).limit(limit + 1)).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode(request.app.state.settings, scope, last.created_at, last.order_id)
    return OrderPage(
        items=[public_order(order, identity) for order in rows[:limit]], next_cursor=next_cursor
    )
