from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, text, tuple_
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import prescription_scope
from app.api.dependencies import DB, Identity, context, token
from app.integrations.upstream import not_found
from app.models import Prescription
from app.pagination import decode, encode, key, scope_for
from app.schemas import (
    IssueInput,
    PrescriptionInput,
    PrescriptionPage,
    PrescriptionPublic,
)
from app.services.issuance import issue_draft
from app.services.records import audit, fields, lock_appointment, prescription_public, replace_items

router = APIRouter(
    prefix="/api/v1/clinical-records",
    tags=["clinical-records"],
    responses={s: {"model": ErrorEnvelope} for s in (401, 404, 409, 422, 502, 503)},
)


@router.post(
    "/appointments/{appointment_id}/prescriptions",
    response_model=PrescriptionPublic,
    status_code=201,
)
def create_prescription(
    appointment_id: UUID, body: PrescriptionInput, request: Request, identity: Identity, session: DB
):
    lock_appointment(session, appointment_id)
    appointment = context(request, identity, appointment_id, write=True)
    if session.scalar(
        select(Prescription.prescription_id).where(
            Prescription.appointment_id == appointment_id, Prescription.status != "voided"
        )
    ):
        raise DomainError(409, "prescription_exists", "Appointment already has a prescription.")
    row = Prescription(**fields(appointment))
    session.add(row)
    session.flush()
    replace_items(
        session, request.app.state.upstream, token(request), request.state.request_id, row, body
    )
    result = prescription_public(session, row)
    session.commit()
    return result


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionPublic)
def update_prescription(
    prescription_id: UUID,
    body: PrescriptionInput,
    request: Request,
    identity: Identity,
    session: DB,
):
    row = session.scalar(
        select(Prescription)
        .where(Prescription.prescription_id == prescription_id)
        .with_for_update()
    )
    if row is None:
        not_found()
    context(request, identity, row.appointment_id, write=True, record=row)
    if row.status != "draft":
        raise DomainError(409, "prescription_immutable", "Only draft prescriptions can be edited.")
    replace_items(
        session, request.app.state.upstream, token(request), request.state.request_id, row, body
    )
    # Replacing children must also touch the parent's update timestamp.
    session.execute(
        text(
            "UPDATE clinical_records.prescriptions SET updated_at = clock_timestamp() "
            "WHERE prescription_id = :id"
        ),
        {"id": prescription_id},
    )
    session.refresh(row)
    result = prescription_public(session, row)
    session.commit()
    return result


@router.post("/prescriptions/{prescription_id}/issue", response_model=PrescriptionPublic)
def issue_prescription(
    prescription_id: UUID,
    request: Request,
    identity: Identity,
    session: DB,
    body: IssueInput | None = None,
):
    row = session.scalar(
        select(Prescription)
        .where(Prescription.prescription_id == prescription_id)
        .with_for_update()
    )
    if row is None:
        not_found()
    context(request, identity, row.appointment_id, write=True, record=row)
    issue_draft(session, row, request.app.state.upstream, token(request), request.state.request_id)
    session.refresh(row)
    result = prescription_public(session, row)
    session.commit()
    return result


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionPublic)
def get_prescription(prescription_id: UUID, request: Request, identity: Identity, session: DB):
    row = session.get(Prescription, prescription_id)
    if row is None:
        not_found()
    context(request, identity, row.appointment_id, record=row)
    result = prescription_public(session, row)
    audit(session, identity.subject_id, request.state.request_id, "prescription", row)
    session.commit()
    return result


@router.get("/prescriptions", response_model=PrescriptionPage)
def list_prescriptions(
    request: Request,
    identity: Identity,
    session: DB,
    appointment_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    settings = request.app.state.settings
    key(settings)
    scope = scope_for(identity, appointment_id)
    position = decode(settings, scope, cursor) if cursor else None
    query = select(Prescription).where(prescription_scope(identity))
    if appointment_id is not None:
        context(request, identity, appointment_id)
        query = query.where(Prescription.appointment_id == appointment_id)
    if position:
        query = query.where(
            tuple_(Prescription.created_at, Prescription.prescription_id) < tuple_(*position)
        )
    rows = session.scalars(
        query.order_by(Prescription.created_at.desc(), Prescription.prescription_id.desc()).limit(
            limit + 1
        )
    ).all()
    # Revalidate current appointment ownership before revealing any record or cursor.
    for row in rows:
        context(request, identity, row.appointment_id, record=row)
    result = PrescriptionPage(
        items=[prescription_public(session, row) for row in rows[:limit]],
        next_cursor=encode(settings, scope, rows[limit - 1]) if len(rows) > limit else None,
    )
    audit(
        session,
        identity.subject_id,
        request.state.request_id,
        "prescription_list",
        appointment_id=appointment_id,
    )
    for row in rows[:limit]:
        audit(session, identity.subject_id, request.state.request_id, "prescription", row)
    session.commit()
    return result
