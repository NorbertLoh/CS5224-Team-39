"""Owning-clinic pickup settings and the minimal delivery projection."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from telelink_common.access import CurrentIdentity, require_tenant_role
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api import DB, clinic_or_404
from app.models import AuditEvent, Clinic, ClinicLocation

router = APIRouter(tags=["clinic-settings"])
Admin = Annotated[CurrentIdentity, Depends(require_tenant_role("clinic_admin"))]
delivery_service = require_service("fulfilment", "telelink-tenant-delivery", "fulfilment_secret")


class Coordinates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: str = Field(pattern=r"^1\.\d{1,7}$")
    lng: str = Field(pattern=r"^10[34]\.\d{1,7}$")

    @field_validator("lat", "lng")
    @classmethod
    def singapore(cls, value, info):
        lower, upper = (
            (Decimal("1.1"), Decimal("1.5"))
            if info.field_name == "lat"
            else (Decimal("103.5"), Decimal("104.1"))
        )
        if not lower <= Decimal(value) <= upper:
            raise ValueError("Choose a location within Singapore")
        return value


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_line: str = Field(min_length=1, max_length=300)
    postal_code: str = Field(pattern=r"^\d{6}$")
    country_code: Literal["SG"] = "SG"
    coordinates: Coordinates
    pickup_contact: "PickupContact | None" = None

    @field_validator("address_line")
    @classmethod
    def plain_address(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a plain address without control characters")
        return value


class PickupContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    phone: str = Field(pattern=r"^\+65[689][0-9]{7}$")

    @field_validator("name")
    @classmethod
    def contact_name(cls, value):
        if not value.strip():
            raise ValueError("Enter a pickup contact name")
        return value.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def singapore_phone(cls, value):
        if isinstance(value, str):
            value = value.translate(str.maketrans("", "", " -()"))
            if len(value) == 8:
                value = "+65" + value
        return value


class ClinicLocationPublic(BaseModel):
    tenant_id: UUID
    location: Location | None


def result(session, tenant_id):
    row = session.get(ClinicLocation, tenant_id)
    return ClinicLocationPublic(tenant_id=tenant_id, location=row.location if row else None)


@router.get("/clinics/{tenant_id}/location", response_model=ClinicLocationPublic)
def read_location(tenant_id: UUID, identity: Admin, session: DB, response: Response):
    clinic_or_404(session, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return result(session, tenant_id)


@router.put("/clinics/{tenant_id}/location", response_model=ClinicLocationPublic)
def save_location(tenant_id: UUID, body: Location, identity: Admin, session: DB):
    clinic = session.scalar(select(Clinic).where(Clinic.tenant_id == tenant_id).with_for_update())
    if clinic is None:
        raise DomainError(404, "not_found", "Resource not found.")
    row = session.get(ClinicLocation, tenant_id)
    value = body.model_dump(mode="json")
    previous = row.location if row else None
    # Older location-only clients must not erase a contact saved by Settings.
    if "pickup_contact" not in body.model_fields_set and previous:
        value["pickup_contact"] = previous.get("pickup_contact")
    if value != previous:
        if row is None:
            row = ClinicLocation(tenant_id=tenant_id)
            session.add(row)
        row.location = value
        row.updated_by = identity.subject_id
        row.updated_at = datetime.now(timezone.utc)
        session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_subject_id=identity.subject_id,
                action="clinic.location_changed",
                previous_values={"location": previous},
                new_values={"location": value},
                reason=None,
            )
        )
        session.commit()
    return result(session, tenant_id)


@router.get(
    "/internal/clinics/{tenant_id}/delivery-location",
    response_model=ClinicLocationPublic,
    dependencies=[Depends(delivery_service)],
)
def delivery_location(tenant_id: UUID, session: DB, response: Response):
    clinic = clinic_or_404(session, tenant_id)
    if clinic.status != "active" or not clinic.membership_provisioned:
        raise DomainError(409, "clinic_not_active", "Clinic is not active.")
    response.headers["Cache-Control"] = "no-store"
    return result(session, tenant_id)
