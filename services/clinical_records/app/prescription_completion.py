"""Issue the saved prescription as part of doctor-driven completion or its retry."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from telelink_common.errors import DomainError

from app.access import assigned_doctor, authorize
from app.api import DB, Identity, context, lock_appointment, token
from app.issuance import issue_draft
from app.models import Prescription
from app.upstream import not_found

router = APIRouter(prefix="/api/v1/clinical-records", tags=["clinical-records"])


class PrescriptionCompletion(BaseModel):
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    doctor_id: UUID
    prescription_id: UUID | None
    status: Literal["none", "issued"]


@router.post(
    "/appointments/{appointment_id}/finalize-prescription",
    response_model=PrescriptionCompletion,
)
def finalize_prescription(appointment_id: UUID, request: Request, identity: Identity, session: DB):
    lock_appointment(session, appointment_id)
    appointment = context(request, identity, appointment_id)
    if not assigned_doctor(identity, appointment):
        not_found()
    if appointment.status not in {"in_progress", "completed"}:
        raise DomainError(409, "consultation_not_started", "Consultation has not started.")
    row = session.scalar(
        select(Prescription)
        .where(Prescription.appointment_id == appointment_id, Prescription.status != "voided")
        .with_for_update()
    )
    if row is not None:
        # Completed visits can finalize an existing saved draft, but cannot edit
        # it or create a new prescription. Retries reuse the issuance/outbox event.
        authorize(identity, appointment, record=row)
        issue_draft(
            session, row, request.app.state.upstream, token(request), request.state.request_id
        )
    result = PrescriptionCompletion(
        **appointment.model_dump(exclude={"status"}),
        prescription_id=row.prescription_id if row else None,
        status="issued" if row else "none",
    )
    session.commit()
    return result
