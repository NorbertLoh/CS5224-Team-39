from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import authorize, prescription_scope
from app.database import get_session
from app.issuance import issue_draft
from app.models import Note, Prescription, PrescriptionItem, ReadAudit
from app.pagination import decode, encode, key, scope_for
from app.schemas import (
    IssueInput,
    ItemPublic,
    NoteInput,
    NotePublic,
    PrescriptionInput,
    PrescriptionPage,
    PrescriptionPublic,
)
from app.upstream import not_found

router = APIRouter(
    prefix="/api/v1/clinical-records",
    tags=["clinical-records"],
    responses={s: {"model": ErrorEnvelope} for s in (401, 404, 409, 422, 502, 503)},
)
DB = Annotated[Session, Depends(get_session)]
Identity = Annotated[CurrentIdentity, Depends(require_identity)]


def token(request):
    return request.headers["authorization"].split(" ", 1)[1]


def context(request, identity, appointment_id, *, write=False, record=None):
    appointment = request.app.state.upstream.appointment(
        appointment_id, token(request), request.state.request_id
    )
    authorize(identity, appointment, write=write, record=record)
    return appointment


def lock_appointment(session, appointment_id):
    # Serialize first inserts too: a row lock cannot lock a nonexistent note.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "clinical-records:" + str(appointment_id)},
    )


def fields(appointment):
    return appointment.model_dump(exclude={"status"})


def audit(session, request, identity, kind, record=None, appointment_id=None):
    session.add(
        ReadAudit(
            actor_id=identity.subject_id,
            resource_type=kind,
            resource_id=(
                getattr(record, "note_id", None)
                or getattr(record, "prescription_id", None)
                or getattr(record, "medical_certificate_id", None)
            ),
            tenant_id=getattr(record, "tenant_id", None),
            appointment_id=getattr(record, "appointment_id", appointment_id),
            request_id=request.state.request_id,
        )
    )


def prescription_public(session, row):
    items = session.scalars(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == row.prescription_id)
        .order_by(PrescriptionItem.prescription_item_id)
    ).all()
    return PrescriptionPublic(
        **{name: getattr(row, name) for name in PrescriptionPublic.model_fields if name != "items"},
        items=[ItemPublic.model_validate(item) for item in items],
    )


def replace_items(session, request, row, body):
    names = request.app.state.upstream.medications(
        row.tenant_id,
        {item.medication_id for item in body.items},
        token(request),
        request.state.request_id,
    )
    session.execute(
        delete(PrescriptionItem).where(PrescriptionItem.prescription_id == row.prescription_id)
    )
    session.add_all(
        [
            PrescriptionItem(
                **item.model_dump(),
                prescription_id=row.prescription_id,
                tenant_id=row.tenant_id,
                display_name=names[item.medication_id],
            )
            for item in body.items
        ]
    )
    session.flush()


@router.put("/appointments/{appointment_id}/note", response_model=NotePublic)
def put_note(
    appointment_id: UUID,
    body: NoteInput,
    request: Request,
    response: Response,
    identity: Identity,
    session: DB,
):
    lock_appointment(session, appointment_id)
    appointment = context(request, identity, appointment_id, write=True)
    row = session.scalar(select(Note).where(Note.appointment_id == appointment_id))
    if row is None:
        row = Note(**fields(appointment), text=body.text)
        session.add(row)
        response.status_code = 201
    else:
        authorize(identity, appointment, write=True, record=row)
        row.text = body.text
    session.flush()
    session.refresh(row)
    result = NotePublic.model_validate(row)
    session.commit()
    return result


@router.get("/appointments/{appointment_id}/note", response_model=NotePublic)
def get_note(appointment_id: UUID, request: Request, identity: Identity, session: DB):
    appointment = context(request, identity, appointment_id)
    row = session.scalar(select(Note).where(Note.appointment_id == appointment_id))
    if row is None:
        not_found()
    authorize(identity, appointment, record=row)
    result = NotePublic.model_validate(row)
    audit(session, request, identity, "note", row)
    session.commit()  # Fail closed: no clinical response if the audit cannot persist.
    return result


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
    replace_items(session, request, row, body)
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
    replace_items(session, request, row, body)
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
    audit(session, request, identity, "prescription", row)
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
    audit(session, request, identity, "prescription_list", appointment_id=appointment_id)
    for row in rows[:limit]:
        audit(session, request, identity, "prescription", row)
    session.commit()
    return result
