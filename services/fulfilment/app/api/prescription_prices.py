"""Clinic-entered prices belong to one issued prescription, never a shared catalogue."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Request, Response
from pydantic import Field, model_validator
from sqlalchemy import delete, select
from telelink_common.errors import DomainError
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.access import require_clinic
from app.api.dependencies import DB, Identity, Patient
from app.models import (
    MAX_MONEY,
    CatalogueItem,
    Order,
    PrescriptionCorrectionHold,
    PrescriptionPrice,
    event_outbox,
)
from app.schemas import Money, StrictModel
from app.services.pricing import saved_prices

router = APIRouter(tags=["prescription-pricing"])


class PatientPricingStatus(StrictModel):
    prescription_id: UUID
    ready: bool


@router.get("/prescriptions/{prescription_id}/pricing-status", response_model=PatientPricingStatus)
def patient_pricing_status(
    prescription_id: UUID, request: Request, response: Response, identity: Patient, session: DB
):
    source = request.app.state.dispensing.get(
        prescription_id, identity.subject_id, request.state.request_id
    )
    if source.prescription_id != prescription_id or source.patient_id != identity.subject_id:
        raise DomainError(404, "not_found", "Resource not found.")
    prices = {
        row.prescription_item_id: row
        for row in saved_prices(session, source.tenant_id, prescription_id)
    }
    per_prescription = source.pricing_mode == "prescription" or bool(prices)
    catalogue = (
        {}
        if per_prescription
        else {
            row.medication_id: row
            for row in session.scalars(
                select(CatalogueItem).where(
                    CatalogueItem.tenant_id == source.tenant_id,
                    CatalogueItem.medication_id.in_([item.medication_id for item in source.items]),
                )
            )
        }
    )
    ready = source.status == "issued" and bool(source.items)
    subtotal = 0
    for item in source.items:
        price = (
            prices.get(item.prescription_item_id)
            if per_prescription
            else catalogue.get(item.medication_id)
        )
        if (
            price is None
            or price.unit_price_minor is None
            or (
                per_prescription
                and (price.medication_id != item.medication_id or price.quantity != item.quantity)
            )
            or (not per_prescription and not price.active)
        ):
            ready = False
        else:
            subtotal += price.unit_price_minor * item.quantity
    ready = (
        ready
        and subtotal <= MAX_MONEY
        and not session.get(PrescriptionCorrectionHold, prescription_id)
    )
    response.headers["Cache-Control"] = "no-store"
    return {"prescription_id": prescription_id, "ready": bool(ready)}


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
    from app.services.orders import lock

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
    # One readiness email per issued prescription, including repeat saves/price edits.
    event_id = uuid5(NAMESPACE_URL, f"telelink:prescription-priced:{prescription_id}")
    if not session.scalar(
        select(event_outbox.c.event_id).where(event_outbox.c.event_id == event_id)
    ):
        add_event(
            session,
            event_outbox,
            new_event(
                "prescription_priced.v1",
                tenant_id=tenant_id,
                correlation_id=prescription_id,
                occurred_at=now,
                event_id=event_id,
                data={"prescription_id": prescription_id, "patient_id": body.patient_id},
            ),
        )
    session.commit()
    return result
