"""Audited operational prescription queue; never expose clinical instructions/notes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, tuple_
from telelink_common.errors import DomainError

from app.api import DB, Identity
from app.models import Prescription, PrescriptionItem, ReadAudit
from app.pagination import decode, encode, scope_for

router = APIRouter(prefix="/api/v1/clinical-records", tags=["prescription-pricing"])


class PricingItem(BaseModel):
    prescription_item_id: UUID
    medication_id: UUID
    display_name: str
    quantity: int


class PricingPrescription(BaseModel):
    prescription_id: UUID
    appointment_id: UUID
    patient_id: UUID
    tenant_id: UUID
    created_at: datetime
    items: list[PricingItem]


class PricingPage(BaseModel):
    items: list[PricingPrescription]
    next_cursor: str | None


@router.get("/clinics/{tenant_id}/prescription-pricing", response_model=PricingPage)
def list_for_pricing(
    tenant_id: UUID,
    request: Request,
    identity: Identity,
    session: DB,
    cursor: str | None = Query(None, max_length=4096),
):
    if not any(
        m.tenant_id == tenant_id and m.status == "active" and "clinic_admin" in m.roles
        for m in identity.memberships
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    scope = scope_for(identity, None) + ["clinic-pricing", str(tenant_id)]
    query = select(Prescription).where(
        Prescription.tenant_id == tenant_id, Prescription.status == "issued"
    )
    if cursor:
        query = query.where(
            tuple_(Prescription.created_at, Prescription.prescription_id)
            < tuple_(*decode(request.app.state.settings, scope, cursor))
        )
    rows = session.scalars(
        query.order_by(Prescription.created_at.desc(), Prescription.prescription_id.desc()).limit(
            26
        )
    ).all()
    items = []
    for row in rows[:25]:
        lines = session.scalars(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == row.prescription_id)
            .order_by(PrescriptionItem.prescription_item_id)
        ).all()
        items.append(
            PricingPrescription(
                prescription_id=row.prescription_id,
                appointment_id=row.appointment_id,
                patient_id=row.patient_id,
                tenant_id=row.tenant_id,
                created_at=row.created_at,
                items=[PricingItem.model_validate(line, from_attributes=True) for line in lines],
            )
        )
    session.add(
        ReadAudit(
            actor_id=identity.subject_id,
            resource_type="prescription_list",
            tenant_id=tenant_id,
            request_id=request.state.request_id,
        )
    )
    session.commit()
    return PricingPage(
        items=items,
        next_cursor=(
            encode(request.app.state.settings, scope, rows[24]) if len(rows) > 25 else None
        ),
    )
