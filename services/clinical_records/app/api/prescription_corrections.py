"""Clinic-admin medication corrections preserve issued originals and their audit trail."""

import hashlib
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from sqlalchemy import select
from telelink_common.errors import DomainError

from app.api.dependencies import DB, Identity, token
from app.issuance import issue_draft
from app.models import Prescription, PrescriptionCorrection, PrescriptionItem
from app.schemas import Input, ItemInput, PrescriptionInput, PrescriptionPublic
from app.services.records import audit, fields, lock_appointment, prescription_public
from app.upstream import not_found

router = APIRouter(prefix="/api/v1/clinical-records", tags=["prescription-corrections"])


class CorrectionInput(Input):
    reason: str = Field(min_length=1, max_length=500)
    items: list[ItemInput] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_items(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("A correction reason is required")
        if self.items:
            PrescriptionInput(items=self.items)
        return self


class CorrectionResult(Input):
    original_prescription_id: UUID
    prescription: PrescriptionPublic | None
    corrected_by: UUID
    reason: str


def admin_record(tenant_id, prescription_id, request, identity, session):
    if not any(
        m.tenant_id == tenant_id and m.status == "active" and "clinic_admin" in m.roles
        for m in identity.memberships
    ):
        not_found()
    row = session.get(Prescription, prescription_id)
    if row is None or row.tenant_id != tenant_id:
        not_found()
    appointment = request.app.state.upstream.appointment(
        row.appointment_id, token(request), request.state.request_id
    )
    if any(
        getattr(row, name) != getattr(appointment, name)
        for name in ("appointment_id", "tenant_id", "patient_id", "doctor_id")
    ):
        not_found()
    if appointment.status not in {"in_progress", "completed"}:
        raise DomainError(
            409,
            "prescription_correction_unavailable",
            "The consultation has not started or was cancelled.",
        )
    return row, appointment


@router.get(
    "/clinics/{tenant_id}/prescriptions/{prescription_id}/correction",
    response_model=PrescriptionPublic,
)
def read_correction(
    tenant_id: UUID, prescription_id: UUID, request: Request, identity: Identity, session: DB
):
    row, _ = admin_record(tenant_id, prescription_id, request, identity, session)
    result = prescription_public(session, row)
    audit(session, identity.subject_id, request.state.request_id, "prescription", row)
    session.commit()
    return result


def correction_result(session, correction):
    replacement = (
        session.get(Prescription, correction.replacement_prescription_id)
        if correction.replacement_prescription_id
        else None
    )
    return CorrectionResult(
        original_prescription_id=correction.original_prescription_id,
        prescription=prescription_public(session, replacement) if replacement else None,
        corrected_by=correction.corrected_by,
        reason=correction.reason,
    )


@router.post(
    "/clinics/{tenant_id}/prescriptions/{prescription_id}/corrections",
    response_model=CorrectionResult,
)
def correct_prescription(
    tenant_id: UUID,
    prescription_id: UUID,
    body: CorrectionInput,
    request: Request,
    identity: Identity,
    session: DB,
):
    row, appointment = admin_record(tenant_id, prescription_id, request, identity, session)
    lock_appointment(session, row.appointment_id)
    row = session.scalar(
        select(Prescription)
        .where(Prescription.prescription_id == prescription_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    previous = session.get(PrescriptionCorrection, prescription_id)
    if previous:
        if previous.fingerprint != fingerprint:
            raise DomainError(
                409, "prescription_already_corrected", "Refresh to edit the current prescription."
            )
        return correction_result(session, previous)
    if row.status != "issued":
        raise DomainError(
            409, "prescription_not_issued", "Only issued prescriptions can be corrected."
        )
    upstream = request.app.state.upstream
    names = (
        upstream.medications(
            tenant_id,
            {item.medication_id for item in body.items},
            token(request),
            request.state.request_id,
        )
        if body.items
        else {}
    )
    # Fulfilment commits a durable hold so an old prescription cannot race a new
    # order/checkout while records commits the replacement. A retry reuses it.
    upstream.prepare_correction(
        tenant_id, row.prescription_id, row.patient_id, token(request), request.state.request_id
    )
    row.status = "voided"
    session.flush()
    replacement = None
    if body.items:
        replacement = Prescription(**fields(appointment), pricing_mode="prescription")
        session.add(replacement)
        session.flush()
        session.add_all(
            [
                PrescriptionItem(
                    **item.model_dump(),
                    prescription_id=replacement.prescription_id,
                    tenant_id=tenant_id,
                    display_name=names[item.medication_id],
                )
                for item in body.items
            ]
        )
        session.flush()
        issue_draft(session, replacement, upstream, token(request), request.state.request_id)
    correction = PrescriptionCorrection(
        original_prescription_id=prescription_id,
        replacement_prescription_id=replacement.prescription_id if replacement else None,
        tenant_id=tenant_id,
        corrected_by=identity.subject_id,
        reason=body.reason,
        fingerprint=fingerprint,
    )
    session.add(correction)
    session.flush()
    result = correction_result(session, correction)
    session.commit()
    return result
