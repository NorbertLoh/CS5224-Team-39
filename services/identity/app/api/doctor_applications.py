"""Applicant-owned submissions and platform-only manual review."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from telelink_common.errors import DomainError

from app.api.dependencies import DB, User
from app.doctor_schemas import ApplicationRead, ApplicationWrite, EventRead, ReviewWrite
from app.models import DoctorApplication, DoctorApplicationEvent, DoctorDocument, Subject
from app.services.doctor_verification import platform_reviewer
from app.services.identity import current_subject

router = APIRouter(tags=["doctor verification"])
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


def conflict():
    return DomainError(409, "application_changed", "Application changed. Reload before continuing.")


def audit(session, application, actor_id, action, reason=None):
    snapshot = ApplicationRead.model_validate(application).model_dump(mode="json")
    if reason is not None:
        snapshot["review_reason"] = reason
    session.add(
        DoctorApplicationEvent(
            subject_id=application.subject_id, actor_id=actor_id, action=action, snapshot=snapshot
        )
    )


@router.get("/me/doctor-application", response_model=ApplicationRead | None)
def mine(principal: User, session: DB):
    subject = current_subject(session, principal)
    return session.get(DoctorApplication, subject.subject_id)


@router.post("/me/doctor-application", response_model=ApplicationRead)
def submit(body: ApplicationWrite, principal: User, session: DB):
    subject = current_subject(session, principal)
    # Serialize first submissions and resubmissions, including competing browser tabs.
    session.scalar(
        select(Subject).where(Subject.subject_id == subject.subject_id).with_for_update()
    )
    application = session.get(DoctorApplication, subject.subject_id)
    if application is not None:
        if application.status != "rejected" or application.revision != body.expected_revision:
            raise conflict()
    elif body.expected_revision != 0:
        raise conflict()
    document = session.get(DoctorDocument, body.document_id)
    if document is None or document.subject_id != subject.subject_id:
        raise DomainError(404, "not_found", "Supporting document not found.")
    values = body.model_dump(exclude={"expected_revision"})
    if application is None:
        application = DoctorApplication(subject_id=subject.subject_id, **values)
        session.add(application)
    else:
        for key, value in values.items():
            setattr(application, key, value)
        application.revision += 1
    application.status = "pending"
    application.rejection_reason = None
    application.reviewed_at = None
    application.reviewer_id = None
    application.submitted_at = datetime.now(timezone.utc)
    session.flush()
    audit(session, application, subject.subject_id, "submitted")
    session.commit()
    return application


@router.post("/me/doctor-documents", status_code=201)
async def upload(request: Request, principal: User, session: DB):
    subject = current_subject(session, principal)
    content_type = request.headers.get("content-type", "").lower()
    if content_type not in {"application/pdf", "image/png", "image/jpeg"}:
        raise DomainError(422, "invalid_document", "Upload a PDF, PNG or JPEG file.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise DomainError(413, "document_too_large", "Supporting files must be at most 5 MB.")
        content.extend(chunk)
    signatures = {
        "application/pdf": b"%PDF-",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
    }
    if not content.startswith(signatures[content_type]):
        raise DomainError(422, "invalid_document", "The file does not match its format.")
    document = DoctorDocument(
        subject_id=subject.subject_id, content_type=content_type, content=bytes(content)
    )
    session.add(document)
    session.flush()
    session.commit()
    return {"document_id": document.document_id}


@router.get("/doctor-documents/{document_id}")
def download(document_id: UUID, principal: User, session: DB):
    subject = current_subject(session, principal)
    document = session.get(DoctorDocument, document_id)
    if document is None or (
        document.subject_id != subject.subject_id and "platform_admin" not in subject.global_roles
    ):
        raise DomainError(404, "not_found", "Document not found.")
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[
        document.content_type
    ]
    return Response(
        document.content,
        media_type=document.content_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="doctor-evidence.{extension}"',
            "Content-Security-Policy": "sandbox",
        },
    )


@router.get("/platform/doctor-applications", response_model=list[ApplicationRead])
def applications(
    principal: User,
    session: DB,
    status: Literal["pending", "approved", "rejected"] = "pending",
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    platform_reviewer(session, principal)
    query = select(DoctorApplication).where(DoctorApplication.status == status)
    if after is not None:
        query = query.where(DoctorApplication.subject_id > after)
    return session.scalars(query.order_by(DoctorApplication.subject_id).limit(limit)).all()


@router.get("/platform/doctor-applications/{subject_id}/history", response_model=list[EventRead])
def history(subject_id: UUID, principal: User, session: DB):
    platform_reviewer(session, principal)
    return session.scalars(
        select(DoctorApplicationEvent)
        .where(DoctorApplicationEvent.subject_id == subject_id)
        .order_by(DoctorApplicationEvent.created_at, DoctorApplicationEvent.event_id)
    ).all()


@router.post("/platform/doctor-applications/{subject_id}/review", response_model=ApplicationRead)
def review(subject_id: UUID, body: ReviewWrite, principal: User, session: DB):
    reviewer = platform_reviewer(session, principal)
    if reviewer.subject_id == subject_id:
        raise DomainError(
            403, "forbidden", "Another platform administrator must review your application."
        )
    session.scalar(select(Subject).where(Subject.subject_id == subject_id).with_for_update())
    application = session.get(DoctorApplication, subject_id)
    if application is None:
        raise DomainError(404, "not_found", "Application not found.")
    if application.status != "pending" or application.revision != body.expected_revision:
        raise conflict()
    application.status = body.decision
    application.rejection_reason = body.reason if body.decision == "rejected" else None
    application.reviewer_id = reviewer.subject_id
    application.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    audit(session, application, reviewer.subject_id, body.decision, body.reason)
    session.commit()
    return application
