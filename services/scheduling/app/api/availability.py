from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import exists, func, or_, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from telelink_common.access import (
    has_tenant_role,
)
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api.dependencies import DB, Doctor, Identity
from app.models import ACTIVE_RESERVATION_STATES, Appointment, AvailabilitySlot
from app.pagination import cursor_key, decode_cursor, encode_cursor
from app.schemas import SlotCreate, SlotPage, SlotPublic, utc_instant
from app.services.holds import expire_slot_holds, server_now

router = APIRouter(
    tags=["availability"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 502, 503)},
)
# S03 expires held/pending reservations in a transaction. A passed Redis TTL
# alone must not release a persisted reservation.
OCCUPIED_STATES = ACTIVE_RESERVATION_STATES


def slot_public(slot, price, occupied=False):
    return SlotPublic(
        **{
            field: getattr(slot, field)
            for field in ("slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at")
        },
        consultation_price=price,
        availability="unavailable" if occupied else "available",
    )


@router.post("/clinics/{tenant_id}/slots", response_model=SlotPublic, status_code=201)
def create_slot(tenant_id: UUID, body: SlotCreate, request: Request, identity: Doctor, session: DB):
    profile = request.app.state.tenant_client.booking_profile(tenant_id, request.state.request_id)
    slot = AvailabilitySlot(
        tenant_id=tenant_id,
        doctor_id=identity.subject_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    # Exclusion constraints can deadlock when both inserts see the other's
    # uncommitted GiST entry. Serialize only this doctor's slot creation across
    # clinics; the exclusion constraint still protects direct database writes.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:doctor, 0))"),
        {"doctor": str(identity.subject_id)},
    )
    if body.starts_at <= datetime.now(timezone.utc):
        raise DomainError(422, "validation_error", "Slot must start in the future.")
    session.add(slot)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if getattr(error.orig.diag, "constraint_name", None) == "ex_slots_doctor_overlap":
            raise DomainError(409, "slot_overlap", "Doctor availability overlaps an existing slot.")
        raise
    return slot_public(slot, profile.consultation_price)


@router.get("/clinics/{tenant_id}/slots", response_model=SlotPage)
def list_slots(
    tenant_id: UUID,
    request: Request,
    session: DB,
    from_at: Annotated[str, Query(alias="from", max_length=64)],
    to_at: Annotated[str, Query(alias="to", max_length=64)],
    doctor_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
):
    try:
        start = utc_instant(datetime.fromisoformat(from_at.replace("Z", "+00:00")))
        end = utc_instant(datetime.fromisoformat(to_at.replace("Z", "+00:00")))
        if not timedelta(0) < end - start <= timedelta(days=7):
            raise ValueError("Invalid date window")
    except ValueError:
        raise DomainError(422, "validation_error", "Use timezone-aware from/to within seven days.")
    settings = request.app.state.settings
    cursor_key(settings)
    scope = [
        str(tenant_id),
        start.isoformat(),
        end.isoformat(),
        str(doctor_id) if doctor_id else None,
    ]
    position = decode_cursor(settings, scope, cursor) if cursor is not None else None
    tenant = request.app.state.tenant_client
    profile = tenant.booking_profile(tenant_id, request.state.request_id, public=True)
    doctors = tenant.active_doctors(tenant_id, request.state.request_id)
    occupied = exists().where(
        Appointment.slot_id == AvailabilitySlot.slot_id,
        Appointment.status.in_(OCCUPIED_STATES),
        or_(
            Appointment.status.not_in(("held", "pending_payment")),
            Appointment.hold_expires_at > func.clock_timestamp(),
        ),
    )
    query = select(AvailabilitySlot, occupied.label("occupied")).where(
        AvailabilitySlot.tenant_id == tenant_id,
        AvailabilitySlot.withdrawn_at.is_(None),
        AvailabilitySlot.doctor_id.in_(list(doctors)),
        AvailabilitySlot.starts_at >= start,
        AvailabilitySlot.starts_at < end,
        AvailabilitySlot.starts_at > datetime.now(timezone.utc),
    )
    if doctor_id is not None:
        query = query.where(AvailabilitySlot.doctor_id == doctor_id)
    if position is not None:
        query = query.where(
            tuple_(AvailabilitySlot.starts_at, AvailabilitySlot.slot_id) > tuple_(*position)
        )
    rows = session.execute(
        query.order_by(AvailabilitySlot.starts_at, AvailabilitySlot.slot_id).limit(limit + 1)
    ).all()
    next_cursor = encode_cursor(settings, scope, rows[limit - 1][0]) if len(rows) > limit else None
    return SlotPage(
        items=[slot_public(slot, profile.consultation_price, busy) for slot, busy in rows[:limit]],
        next_cursor=next_cursor,
    )


@router.delete("/slots/{slot_id}", status_code=204)
def delete_slot(slot_id: UUID, request: Request, identity: Identity, session: DB):
    slot = session.scalar(
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.slot_id == slot_id,
            AvailabilitySlot.withdrawn_at.is_(None),
        )
        .with_for_update()
    )
    membership = next(
        (item for item in identity.memberships if slot and item.tenant_id == slot.tenant_id), None
    )
    if (
        slot is None
        or slot.doctor_id != identity.subject_id
        or not has_tenant_role(membership, slot.tenant_id, "doctor")
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    expire_slot_holds(session, slot_id, server_now(session), request.app.state.hold_cache)
    reserved = session.scalar(
        select(
            exists().where(Appointment.slot_id == slot_id, Appointment.status.in_(OCCUPIED_STATES))
        )
    )
    if reserved:
        raise DomainError(409, "slot_reserved", "Slot has an active reservation.")
    slot.withdrawn_at = datetime.now(timezone.utc)
    session.commit()
    return Response(status_code=204)
