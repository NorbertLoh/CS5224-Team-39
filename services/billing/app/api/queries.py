"""Read-only billing views; identity is refreshed on every request."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, tuple_
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import Database, Identity
from app.models import Payment
from app.pagination import cursor_key, decode_cursor, encode_cursor
from app.schemas import CommissionTotals, Money, PaymentPage, PaymentPublic, payment_public
from app.services.queries import access_scope

router = APIRouter(
    responses={s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 422, 502, 503)}
)
Purpose = Literal["consultation", "medication_delivery"]
Status = Literal["pending", "succeeded", "failed", "refund_pending", "refunded", "refund_failed"]


@router.get("/payments", response_model=PaymentPage)
def list_payments(
    request: Request,
    identity: Identity,
    session: Database,
    tenant_id: UUID | None = None,
    purpose: Purpose | None = None,
    status: Status | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
):
    predicate, scope = access_scope(identity)
    scope.update(tenant_id=str(tenant_id) if tenant_id else None, purpose=purpose, status=status)
    settings = request.app.state.settings
    cursor_key(settings)
    query = select(Payment).where(predicate)
    for column, value in (
        (Payment.tenant_id, tenant_id),
        (Payment.purpose, purpose),
        (Payment.status, status),
    ):
        if value is not None:
            query = query.where(column == value)
    if cursor is not None:
        created_at, payment_id = decode_cursor(settings, scope, cursor)
        query = query.where(
            tuple_(Payment.created_at, Payment.payment_id) < (created_at, payment_id)
        )
    rows = session.scalars(
        query.order_by(Payment.created_at.desc(), Payment.payment_id.desc()).limit(limit + 1)
    ).all()
    return PaymentPage(
        items=[payment_public(row) for row in rows[:limit]],
        next_cursor=encode_cursor(settings, scope, rows[limit - 1]) if len(rows) > limit else None,
    )


@router.get("/payments/{payment_id}", response_model=PaymentPublic)
def get_payment(payment_id: UUID, identity: Identity, session: Database):
    predicate, _ = access_scope(identity, conceal=True)
    payment = session.scalar(select(Payment).where(predicate, Payment.payment_id == payment_id))
    if payment is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return payment_public(payment)


@router.get("/commission-totals", response_model=CommissionTotals)
def commission_totals(
    identity: Identity,
    session: Database,
    tenant_id: UUID | None = None,
    purpose: Purpose | None = None,
):
    predicate, _ = access_scope(identity, admin_only=True)
    columns = (Payment.amount_minor, Payment.commission_amount_minor, Payment.clinic_amount_minor)
    query = select(func.count(), *(func.coalesce(func.sum(c), 0) for c in columns)).where(
        predicate, Payment.status == "succeeded", Payment.resolution == "none"
    )
    if tenant_id is not None:
        query = query.where(Payment.tenant_id == tenant_id)
    if purpose is not None:
        query = query.where(Payment.purpose == purpose)
    count, *amounts = session.execute(query).one()
    if any(value > 9007199254740991 for value in amounts):
        raise DomainError(409, "totals_limit_exceeded", "Totals exceed the supported money range.")
    return CommissionTotals(
        payment_count=count,
        **{
            name: Money(amount_minor=int(value), currency="SGD")
            for name, value in zip(("amount", "commission_amount", "clinic_amount"), amounts)
        },
    )
