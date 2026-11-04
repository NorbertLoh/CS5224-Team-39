"""Doctor drafts and a service-only, idempotent completion handoff."""

from datetime import date, timedelta
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator
from sqlalchemy import func, select
from telelink_common.errors import DomainError
from telelink_common.events import new_event
from telelink_common.outbox import add_event
from telelink_common.service_auth import require_service

from app.access import assigned_doctor, authorize
from app.api.dependencies import DB, Identity, context
from app.integrations.upstream import not_found
from app.models import MedicalCertificate, event_outbox
from app.schemas import Input, RecordPublic
from app.services.records import audit, fields, lock_appointment

router = APIRouter(prefix="/api/v1/clinical-records", tags=["medical-certificates"])


class MCInput(Input):
    selected: StrictBool = False
    start_date: date | None = None
    duration_days: Annotated[int, Field(strict=True, gt=0, le=3652059)] | None = None
    additional_notes: str = Field(default="", max_length=20000)

    @field_validator("start_date", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if value is not None and (not isinstance(value, str) or len(value) != 10):
            raise ValueError("Use a Singapore calendar date in YYYY-MM-DD form")
        return value

    @model_validator(mode="after")
    def period(self):
        if self.selected and (self.start_date is None or self.duration_days is None):
            raise ValueError("MC start date and positive whole-number duration are required")
        if self.start_date is not None and self.duration_days is not None:
            try:
                self.start_date + timedelta(days=self.duration_days - 1)
            except (OverflowError, ValueError):
                raise ValueError("MC end date is out of range") from None
        self.additional_notes = self.additional_notes.strip()
        return self


class MCPublic(RecordPublic):
    medical_certificate_id: UUID
    selected: bool
    start_date: date | None
    duration_days: int | None
    additional_notes: str
    consultation_date: date | None
    finalized_at: AwareDatetime | None
    issued_at: AwareDatetime | None
    end_date: date | None


class Completion(Input):
    tenant_id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    consultation_date: date
    completed_at: AwareDatetime


@router.get("/appointments/{appointment_id}/medical-certificate", response_model=MCPublic)
def read_mc(appointment_id: UUID, request: Request, identity: Identity, session: DB):
    appointment = context(request, identity, appointment_id)
    row = session.scalar(
        select(MedicalCertificate).where(MedicalCertificate.appointment_id == appointment_id)
    )
    if row is None:
        not_found()
    # Patients may see an issued MC; unissued doctor drafts remain private.
    authorize(identity, appointment, record=row)
    if row.issued_at is None and not assigned_doctor(identity, appointment):
        not_found()
    result = MCPublic.model_validate(row)
    audit(session, identity.subject_id, request.state.request_id, "medical_certificate", row)
    session.commit()
    return result


@router.put("/appointments/{appointment_id}/medical-certificate", response_model=MCPublic)
def save_mc(appointment_id: UUID, body: MCInput, request: Request, identity: Identity, session: DB):
    lock_appointment(session, appointment_id)
    appointment = context(request, identity, appointment_id, write=True)
    row = session.scalar(
        select(MedicalCertificate).where(MedicalCertificate.appointment_id == appointment_id)
    )
    if row is None:
        row = MedicalCertificate(**fields(appointment))
        session.add(row)
    else:
        authorize(identity, appointment, write=True, record=row)
        if row.finalized_at is not None:
            raise DomainError(409, "mc_finalized", "The MC decision is already finalized.")
    for name, value in body.model_dump().items():
        setattr(row, name, value)
    session.flush()
    session.refresh(row)
    result = MCPublic.model_validate(row)
    session.commit()
    return result


@router.post("/internal/appointments/{appointment_id}/complete-mc", response_model=MCPublic)
def complete_mc(
    appointment_id: UUID,
    body: Completion,
    request: Request,
    session: DB,
    caller: Annotated[
        str,
        Depends(
            require_service("consultation", "telelink-records-consultation", "consultation_secret")
        ),
    ],
):
    # Only consultation can attest completion, after both its local end and the
    # scheduling handoff succeeded. Browser fields cannot attest or issue an MC.
    if body.appointment_id != appointment_id:
        not_found()
    lock_appointment(session, appointment_id)
    row = session.scalar(
        select(MedicalCertificate).where(MedicalCertificate.appointment_id == appointment_id)
    )
    links = body.model_dump(include={"tenant_id", "appointment_id", "patient_id", "doctor_id"})
    if row is None:
        # Persist even an absent/disabled draft, sealing the no-MC decision.
        row = MedicalCertificate(**links, selected=False, additional_notes="")
        session.add(row)
        session.flush()
    if any(getattr(row, key) != value for key, value in links.items()):
        not_found()
    if row.finalized_at is None:
        row.finalized_at = body.completed_at
        row.consultation_date = body.consultation_date
        if row.selected:
            row.issued_at = session.scalar(select(func.clock_timestamp()))
            add_event(
                session,
                event_outbox,
                new_event(
                    "medical_certificate_issued.v1",
                    event_id=uuid5(
                        NAMESPACE_URL, "telelink:mc_issued:" + str(row.medical_certificate_id)
                    ),
                    occurred_at=row.issued_at,
                    tenant_id=row.tenant_id,
                    correlation_id=request.state.request_id,
                    data={
                        "medical_certificate_id": row.medical_certificate_id,
                        "appointment_id": row.appointment_id,
                        "patient_id": row.patient_id,
                        "doctor_id": row.doctor_id,
                    },
                ),
            )
    elif row.finalized_at != body.completed_at or row.consultation_date != body.consultation_date:
        raise DomainError(409, "mc_completion_conflict", "Completion context has changed.")
    session.flush()
    session.refresh(row)
    result = MCPublic.model_validate(row)
    session.commit()
    return result
