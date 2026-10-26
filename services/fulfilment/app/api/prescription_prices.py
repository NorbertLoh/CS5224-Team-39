"""Clinic-entered prices belong to one issued prescription, never a shared catalogue."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from sqlalchemy import delete, select
from telelink_common.errors import DomainError

from app.access import require_clinic
from app.api.dependencies import DB, Identity
from app.models import MAX_MONEY, Order, PrescriptionPrice
from app.schemas import Money, StrictModel

router = APIRouter(tags=["prescription-pricing"])


class PriceLine(StrictModel):
    prescription_item_id: UUID
    unit_price: Money


class PriceInput(StrictModel):
    patient_id: UUID
    items: list[PriceLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.prescription_item_id for line in self.items}) != len(self.items):
            raise ValueError("Duplicate prescription item")
        return self


class PriceResult(StrictModel):
    prescription_id: UUID
    locked: bool
    items: list[PriceLine]


def saved_prices(session, tenant_id, prescription_id):
    return list(
        session.scalars(
            select(PrescriptionPrice)
            .where(
                PrescriptionPrice.tenant_id == tenant_id,
                PrescriptionPrice.prescription_id == prescription_id,
            )
            .order_by(PrescriptionPrice.prescription_item_id)
        )
    )


def price_result(session, tenant_id, prescription_id):
    order = session.scalar(
        select(Order).where(Order.tenant_id == tenant_id, Order.prescription_id == prescription_id)
    )
    rows = saved_prices(session, tenant_id, prescription_id)
    # Legacy orders retain their original trusted item snapshots.
    if not rows and order is not None:
        rows = order.items
    return PriceResult(
        prescription_id=prescription_id,
        locked=order is not None,
        items=[
            PriceLine(
                prescription_item_id=row.prescription_item_id,
                unit_price=Money(amount_minor=row.unit_price_minor, currency="SGD"),
            )
            for row in rows
        ],
    )


@router.get(
    "/clinics/{tenant_id}/prescriptions/{prescription_id}/prices", response_model=PriceResult
)
def get_prices(tenant_id: UUID, prescription_id: UUID, identity: Identity, session: DB):
    require_clinic(identity, tenant_id, {"clinic_admin"})
    return price_result(session, tenant_id, prescription_id)


@router.put(
    "/clinics/{tenant_id}/prescriptions/{prescription_id}/prices", response_model=PriceResult
)
def put_prices(
    tenant_id: UUID,
    prescription_id: UUID,
    body: PriceInput,
    request: Request,
    identity: Identity,
    session: DB,
):
    from app.api.orders import lock

    require_clinic(identity, tenant_id, {"clinic_admin"})
    lock(session, f"orders:prescription:{prescription_id}")
    context = request.app.state.dispensing.get(
        prescription_id, body.patient_id, request.state.request_id
    )
    if (context.tenant_id, context.patient_id, context.prescription_id) != (
        tenant_id,
        body.patient_id,
        prescription_id,
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    if context.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
    lines = {line.prescription_item_id: line for line in context.items}
    submitted = {line.prescription_item_id: line.unit_price.amount_minor for line in body.items}
    if submitted.keys() != lines.keys():
        raise DomainError(422, "validation_error", "Price every prescribed item exactly once.")
    if any(not line.display_name for line in lines.values()):
        raise DomainError(502, "upstream_error", "Prescription names are unavailable.")
    if sum(submitted[key] * line.quantity for key, line in lines.items()) > MAX_MONEY:
        raise DomainError(422, "amount_out_of_range", "Prescription total exceeds supported range.")
    existing = price_result(session, tenant_id, prescription_id)
    if existing.locked:
        if {
            line.prescription_item_id: line.unit_price.amount_minor for line in existing.items
        } == submitted:
            return existing
        raise DomainError(
            409, "prescription_price_locked", "Prices are locked after an order is opened."
        )
    session.execute(
        delete(PrescriptionPrice).where(
            PrescriptionPrice.tenant_id == tenant_id,
            PrescriptionPrice.prescription_id == prescription_id,
        )
    )
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            PrescriptionPrice(
                tenant_id=tenant_id,
                prescription_id=prescription_id,
                prescription_item_id=key,
                medication_id=line.medication_id,
                display_name=line.display_name,
                quantity=line.quantity,
                unit_price_minor=submitted[key],
                priced_by=identity.subject_id,
                updated_at=now,
            )
            for key, line in lines.items()
        ]
    )
    session.flush()
    result = price_result(session, tenant_id, prescription_id)
    session.commit()
    return result
