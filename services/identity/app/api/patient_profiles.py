"""Self-service patient contact details, with a minimal delivery projection."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import DB, User
from app.models import PatientProfile, Subject
from app.services.identity import current_subject

router = APIRouter(tags=["patient-profile"])
delivery_service = require_service("fulfilment", "telelink-identity-delivery", "fulfilment_secret")


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(pattern=r"^\+65[689][0-9]{7}$")
    address_line: str = Field(min_length=1, max_length=300)
    postal_code: str = Field(pattern=r"^[0-9]{6}$")
    country_code: Literal["SG"] = "SG"

    @field_validator("name", "address_line")
    @classmethod
    def nonblank_plain_text(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Enter plain text without control characters")
        return value

    @field_validator("phone_number", mode="before")
    @classmethod
    def singapore_phone(cls, value):
        if isinstance(value, str):
            value = value.translate(str.maketrans("", "", " -()"))
            if len(value) == 8:
                value = "+65" + value
        return value


class ProfileRead(BaseModel):
    subject_id: UUID
    name: str
    phone_number: str
    address_line: str
    postal_code: str
    country_code: Literal["SG"] = "SG"


def patient(session, principal):
    subject = current_subject(session, principal)
    if "patient" not in subject.global_roles:
        raise DomainError(403, "patient_required", "Patient access required.")
    return subject


def profile(session, subject):
    row = session.get(PatientProfile, subject.subject_id)
    return ProfileRead(
        subject_id=subject.subject_id,
        name=subject.display_name,
        phone_number=row.phone_number if row else "",
        address_line=row.address_line if row else "",
        postal_code=row.postal_code if row else "",
    )


@router.get("/me/patient-profile", response_model=ProfileRead)
def read_profile(principal: User, session: DB, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return profile(session, patient(session, principal))


@router.put("/me/patient-profile", response_model=ProfileRead)
def save_profile(body: ProfileWrite, principal: User, session: DB, response: Response):
    subject = patient(session, principal)
    subject = session.scalar(
        select(Subject).where(Subject.subject_id == subject.subject_id).with_for_update()
    )
    row = session.get(PatientProfile, subject.subject_id)
    if row is None:
        row = PatientProfile(subject_id=subject.subject_id)
        session.add(row)
    subject.display_name = body.name
    for key, value in body.model_dump(exclude={"name"}).items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return profile(session, subject)


class DeliveryContact(BaseModel):
    patient_id: UUID
    name: str
    phone: str


@router.get(
    "/internal/patients/{patient_id}/delivery-contact",
    response_model=DeliveryContact,
    dependencies=[Depends(delivery_service)],
)
def delivery_contact(patient_id: UUID, session: DB, response: Response):
    subject = session.get(Subject, patient_id)
    row = session.get(PatientProfile, patient_id)
    if subject is None or "patient" not in subject.global_roles or row is None:
        raise DomainError(404, "not_found", "Patient delivery contact is unavailable.")
    response.headers["Cache-Control"] = "no-store"
    return DeliveryContact(patient_id=patient_id, name=subject.display_name, phone=row.phone_number)
