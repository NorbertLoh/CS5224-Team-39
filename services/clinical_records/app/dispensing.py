"""Minimal, audited dispensing projection for authenticated fulfilment callers."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api import DB
from app.models import Prescription, PrescriptionItem, ServiceReadAudit

router = APIRouter(prefix="/api/v1/clinical-records/internal", tags=["internal"])
fulfilment = require_service("fulfilment", "telelink-records-fulfilment", "fulfilment_secret")


class Item(BaseModel):
    prescription_item_id: UUID
    medication_id: UUID
    quantity: int


class Projection(BaseModel):
    prescription_id: UUID
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    status: Literal["issued"]
    items: list[Item]


@router.get("/prescriptions/{prescription_id}/dispensing", response_model=Projection)
def dispensing_projection(
    prescription_id: UUID,
    patient_id: UUID,
    purpose: Literal["dispensing"],
    request: Request,
    session: DB,
    caller: Annotated[str, Depends(fulfilment)],
):
    row = session.get(Prescription, prescription_id)
    if row is None or row.patient_id != patient_id:
        raise DomainError(404, "not_found", "Resource not found.")
    if row.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
    items = session.scalars(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == prescription_id)
        .order_by(PrescriptionItem.prescription_item_id)
    ).all()
    result = Projection(
        prescription_id=row.prescription_id,
        appointment_id=row.appointment_id,
        tenant_id=row.tenant_id,
        patient_id=row.patient_id,
        status=row.status,
        items=[
            Item(
                prescription_item_id=item.prescription_item_id,
                medication_id=item.medication_id,
                quantity=item.quantity,
            )
            for item in items
        ],
    )
    session.add(
        ServiceReadAudit(
            caller=caller,
            purpose=purpose,
            prescription_id=prescription_id,
            tenant_id=row.tenant_id,
            appointment_id=row.appointment_id,
            request_id=request.state.request_id,
        )
    )
    session.commit()
    return result
