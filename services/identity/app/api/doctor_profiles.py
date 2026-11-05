"""Doctor-owned profile photo writes and public, eligibility-checked portraits."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from telelink_common.errors import DomainError

from app.api.dependencies import DB, User
from app.models import DoctorPhoto, Membership, Subject
from app.services.doctor_photos import MAX_PHOTO_BYTES, PHOTO_TYPES, sanitize_photo
from app.services.doctor_verification import approved_doctor
from app.services.identity import current_subject

router = APIRouter(tags=["doctor profile"])


class PhotoRead(BaseModel):
    doctor_id: UUID
    photo_id: UUID | None


def eligible_doctor(session, subject_id):
    return (
        session.scalar(
            select(Membership.membership_id)
            .where(
                Membership.subject_id == subject_id,
                Membership.status == "active",
                Membership.roles.any("doctor"),
                approved_doctor(Membership.subject_id),
            )
            .limit(1)
        )
        is not None
    )


def own_doctor(session, principal):
    subject = current_subject(session, principal)
    if not eligible_doctor(session, subject.subject_id):
        raise DomainError(403, "forbidden", "An active approved doctor account is required.")
    return subject


@router.get("/me/doctor-profile", response_model=PhotoRead)
def mine(principal: User, session: DB):
    subject = own_doctor(session, principal)
    photo = session.get(DoctorPhoto, subject.subject_id)
    return PhotoRead(doctor_id=subject.subject_id, photo_id=photo.photo_id if photo else None)


@router.put("/me/doctor-profile/photo", response_model=PhotoRead)
async def upload(request: Request, principal: User, session: DB):
    subject = own_doctor(session, principal)
    content_type = request.headers.get("content-type", "").lower()
    if content_type not in PHOTO_TYPES:
        raise DomainError(422, "invalid_photo", "Upload a PNG or JPEG photo.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_PHOTO_BYTES:
            raise DomainError(413, "photo_too_large", "Photos must be at most 2 MB.")
        content.extend(chunk)
    sanitized = await run_in_threadpool(sanitize_photo, bytes(content), content_type)
    # Serialize uploads/removal from competing tabs, including the first upload.
    session.scalar(
        select(Subject).where(Subject.subject_id == subject.subject_id).with_for_update()
    )
    photo = session.get(DoctorPhoto, subject.subject_id)
    if photo is None:
        photo = DoctorPhoto(subject_id=subject.subject_id)
        session.add(photo)
    photo.photo_id = uuid4()
    photo.content = sanitized
    session.commit()
    return PhotoRead(doctor_id=subject.subject_id, photo_id=photo.photo_id)


@router.delete("/me/doctor-profile/photo", status_code=204)
def remove(principal: User, session: DB):
    subject = own_doctor(session, principal)
    session.scalar(
        select(Subject).where(Subject.subject_id == subject.subject_id).with_for_update()
    )
    photo = session.get(DoctorPhoto, subject.subject_id)
    if photo is not None:
        session.delete(photo)
    session.commit()
    return Response(status_code=204)


@router.get("/doctors/{doctor_id}/photos/{photo_id}")
def public_photo(doctor_id: UUID, photo_id: UUID, session: DB):
    if not eligible_doctor(session, doctor_id):
        raise DomainError(404, "not_found", "Photo not found.")
    photo = session.get(DoctorPhoto, doctor_id)
    if photo is None or photo.photo_id != photo_id:
        raise DomainError(404, "not_found", "Photo not found.")
    return Response(
        photo.content,
        media_type="image/jpeg",
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"},
    )
