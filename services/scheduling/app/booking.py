from datetime import timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telelink_common.access import CurrentIdentity, require_global_role
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api import DB
from app.holds import expire_slot_holds, server_now
from app.models import ACTIVE_RESERVATION_STATES, Appointment, AvailabilitySlot
from app.schemas import AppointmentPublic, HoldCreate, Money

router = APIRouter(
    tags=["booking"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 502, 503)},
)
Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]


def appointment_public(appointment):
    return AppointmentPublic(
        **{
            field: getattr(appointment, field)
            for field in (
                "appointment_id",
                "tenant_id",
                "patient_id",
                "doctor_id",
                "slot_id",
                "status",
                "starts_at",
                "ends_at",
                "hold_expires_at",
                "payment_id",
                "payment_resolution",
                "created_at",
                "updated_at",
            )
        },
        consultation_price=Money(
            amount_minor=appointment.consultation_price_minor, currency=appointment.currency
        ),
    )


@router.post("/appointments", response_model=AppointmentPublic, status_code=201)
def create_hold(body: HoldCreate, request: Request, identity: Patient, session: DB):
    cache = request.app.state.hold_cache
    if cache.client is None:
        raise DomainError(503, "unavailable", "Hold cache is not configured.")
    # HTTP checks happen before database locks, keeping reservation transactions short.
    tenant = request.app.state.tenant_client
    profile = tenant.booking_profile(body.tenant_id, request.state.request_id)
    doctors = tenant.active_doctors(body.tenant_id, request.state.request_id)
    slot = session.scalar(
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.slot_id == body.slot_id,
            AvailabilitySlot.tenant_id == body.tenant_id,
            AvailabilitySlot.withdrawn_at.is_(None),
        )
        .with_for_update()
    )
    if slot is None:
        raise DomainError(404, "not_found", "Resource not found.")
    if slot.doctor_id not in doctors:
        raise DomainError(409, "slot_unavailable", "Slot cannot be reserved.")
    now = server_now(session)
    if slot.starts_at <= now:
        raise DomainError(409, "slot_unavailable", "Slot cannot be reserved.")
    expire_slot_holds(session, slot.slot_id, now, cache)
    existing = session.scalar(
        select(Appointment).where(
            Appointment.slot_id == slot.slot_id, Appointment.status.in_(ACTIVE_RESERVATION_STATES)
        )
    )
    if existing is not None:
        raise DomainError(409, "slot_unavailable", "Slot cannot be reserved.")
    appointment = Appointment(
        appointment_id=uuid4(),
        tenant_id=slot.tenant_id,
        slot_id=slot.slot_id,
        patient_id=identity.subject_id,
        doctor_id=slot.doctor_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        status="held",
        payment_resolution="none",
        created_at=now,
        updated_at=now,
        hold_expires_at=min(now + timedelta(minutes=10), slot.starts_at),
        consultation_price_minor=profile.consultation_price.amount_minor,
        currency=profile.consultation_price.currency,
    )
    appointment_id = appointment.appointment_id
    session.add(appointment)
    expired_before_commit = False
    try:
        session.flush()
        # Publish while holding the slot lock. Later expiry/reallocation cannot
        # race a delayed cache write from this transaction. PostgreSQL stays truth.
        cache.mirror(appointment)
        if server_now(session) >= appointment.hold_expires_at:
            appointment.status = "expired"
            cache.release(body.slot_id, appointment_id)
            expired_before_commit = True
        session.commit()
    except Exception as error:
        session.rollback()
        cache.release(body.slot_id, appointment_id)
        if (
            isinstance(error, IntegrityError)
            and getattr(error.orig.diag, "constraint_name", None) == "uq_appointments_active_slot"
        ):
            raise DomainError(409, "slot_unavailable", "Slot cannot be reserved.") from None
        raise
    if expired_before_commit:
        raise DomainError(409, "hold_expired", "The booking hold has expired.")
    return appointment_public(appointment)
