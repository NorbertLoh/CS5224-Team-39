from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import false, or_, select, tuple_
from telelink_common.errors import ErrorEnvelope

from app.access import authorize, not_found
from app.api.dependencies import DB, Identity
from app.models import AccessAudit, Document
from app.pagination import decode, encode, key, scope_for
from app.schemas import DocumentPage, DocumentPublic, DownloadPublic

router = APIRouter(
    prefix="/api/v1/document/documents",
    tags=["documents"],
    responses={s: {"model": ErrorEnvelope} for s in (401, 404, 409, 422, 502, 503)},
)


def context(request, identity, appointment_id, row=None):
    appointment = request.app.state.appointments.appointment(
        appointment_id, request.headers["authorization"].split(" ", 1)[1], request.state.request_id
    )
    authorize(identity, appointment, row)
    return appointment


def document_scope(identity):
    predicates = [false()]
    if "patient" in identity.global_roles:
        predicates.append(Document.patient_id == identity.subject_id)
    for membership in identity.memberships:
        if membership.status == "active" and "doctor" in membership.roles:
            predicates.append(
                (Document.tenant_id == membership.tenant_id)
                & (Document.doctor_id == identity.subject_id)
            )
    return or_(*predicates)


def audit(session, request, identity, action, row=None, appointment=None):
    session.add(
        AccessAudit(
            actor_id=identity.subject_id,
            action=action,
            document_id=row.document_id if row else None,
            tenant_id=row.tenant_id if row else getattr(appointment, "tenant_id", None),
            appointment_id=row.appointment_id
            if row
            else getattr(appointment, "appointment_id", None),
            request_id=request.state.request_id,
        )
    )


@router.get("", response_model=DocumentPage)
def list_documents(
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
    query = select(Document).where(document_scope(identity))
    appointments = {}
    if appointment_id is not None:
        appointments[appointment_id] = context(request, identity, appointment_id)
        query = query.where(Document.appointment_id == appointment_id)
    if position:
        query = query.where(tuple_(Document.created_at, Document.document_id) < tuple_(*position))
    rows = session.scalars(
        query.order_by(Document.created_at.desc(), Document.document_id.desc()).limit(limit + 1)
    ).all()
    for row in rows:
        if row.appointment_id not in appointments:
            appointments[row.appointment_id] = context(request, identity, row.appointment_id)
        authorize(identity, appointments[row.appointment_id], row)
    result = DocumentPage(
        items=[DocumentPublic.model_validate(row) for row in rows[:limit]],
        next_cursor=encode(settings, scope, rows[limit - 1]) if len(rows) > limit else None,
    )
    audit(session, request, identity, "list", appointment=appointments.get(appointment_id))
    for row in rows[:limit]:
        audit(session, request, identity, "read", row)
    session.commit()  # Fail closed: no metadata leaves the service without a durable audit.
    return result


@router.get("/{document_id}/download", response_model=DownloadPublic)
def download_document(document_id: UUID, request: Request, identity: Identity, session: DB):
    row = session.scalar(
        select(Document).where(Document.document_id == document_id, document_scope(identity))
    )
    if row is None:
        not_found()
    context(request, identity, row.appointment_id, row)
    downloads = request.app.state.downloads
    downloads.prepare(row)
    audit(session, request, identity, "download", row)
    session.commit()  # Persist access intent before minting a bearer URL.
    return downloads.sign(row)
