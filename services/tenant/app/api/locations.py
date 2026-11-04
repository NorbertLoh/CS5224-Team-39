"""Owning-clinic pickup settings and the minimal delivery projection."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import DB
from app.api.dependencies import PickupAdmin as Admin
from app.location_schemas import Location
from app.models import AuditEvent, Clinic, ClinicLocation
from app.services.clinics import clinic_or_404

router = APIRouter(tags=["clinic-settings"])
delivery_service = require_service("fulfilment", "telelink-tenant-delivery", "fulfilment_secret")


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
