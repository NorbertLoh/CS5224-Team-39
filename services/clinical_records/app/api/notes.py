from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from telelink_common.errors import ErrorEnvelope

from app.access import authorize
from app.api.dependencies import DB, Identity, context
from app.models import Note
from app.schemas import (
    NoteInput,
    NotePublic,
)
from app.services.records import audit, fields, lock_appointment
from app.upstream import not_found

router = APIRouter(
    prefix="/api/v1/clinical-records",
    tags=["clinical-records"],
    responses={s: {"model": ErrorEnvelope} for s in (401, 404, 409, 422, 502, 503)},
)


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
    audit(session, identity.subject_id, request.state.request_id, "note", row)
    session.commit()  # Fail closed: no clinical response if the audit cannot persist.
    return result
