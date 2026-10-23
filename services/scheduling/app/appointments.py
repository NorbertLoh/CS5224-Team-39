from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, case, func, select, tuple_
from telelink_common.access import CurrentIdentity, require_identity
from telelink_common.errors import DomainError, ErrorEnvelope

from app.api import DB
from app.appointment_access import (
    appointment_scope,
    authorization_scope,
    can_access,
    require_collection_tenant,
)
from app.booking import appointment_public
from app.holds import expire_slot_holds, server_now
from app.models import Appointment
from app.pagination import cursor_key, decode_appointment_cursor, encode_appointment_cursor
from app.schemas import AppointmentPage, AppointmentPublic, Cancellation, utc_instant
from app.service_auth import require_consultation, require_operator
from app.transitions import (
    cancel_appointment,
    consultation_action,
    invalid_transition,
    lock_appointment,
)

router = APIRouter(
    tags=["appointments"],
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422, 502, 503)},
)
Identity = Annotated[CurrentIdentity, Depends(require_identity)]
AppointmentStatus = Literal[
    "held",
    "pending_payment",
    "confirmed",
    "in_progress",
    "completed",
    "expired",
    "cancelled",
    "no_show",
]


def effective_status():
    return case(
        (
            Appointment.status.in_(("held", "pending_payment"))
            & (Appointment.hold_expires_at <= func.statement_timestamp()),
            "expired",
        ),
        else_=Appointment.status,
    )


def date_filter(value):
    if value is None:
        return None
    try:
        return utc_instant(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        raise DomainError(
            422, "validation_error", "Use timezone-aware appointment date filters."
        ) from None


def visible_appointment(session, appointment_id, identity, *, cancel=False):
    appointment = session.get(Appointment, appointment_id)
    if appointment is None or not can_access(identity, appointment, cancel=cancel):
        raise DomainError(404, "not_found", "Resource not found.")
    return appointment


@router.get("/appointments", response_model=AppointmentPage)
def list_appointments(
    request: Request,
    identity: Identity,
    session: DB,
    tenant_id: UUID | None = None,
    status: AppointmentStatus | None = None,
    from_at: Annotated[str | None, Query(alias="from", max_length=64)] = None,
    to_at: Annotated[str | None, Query(alias="to", max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=4096)] = None,
    period: Literal["upcoming", "past"] | None = None,
):
    scope_predicate = appointment_scope(identity)
    require_collection_tenant(identity, tenant_id)
    start, end = date_filter(from_at), date_filter(to_at)
    if start is not None and end is not None and start >= end:
        raise DomainError(422, "validation_error", "from must precede to.")
    settings = request.app.state.settings
    cursor_key(settings)
    scope = [
        authorization_scope(identity),
        str(tenant_id) if tenant_id else None,
        status,
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    ]
    if period is not None:
        scope.extend([period, "desc" if period == "past" else "asc"])
    position = decode_appointment_cursor(settings, scope, cursor) if cursor is not None else None
    current_status = effective_status()
    query = select(Appointment, current_status).where(scope_predicate)
    if period is not None:
        upcoming = and_(
            current_status.in_(("held", "pending_payment", "confirmed", "in_progress")),
            Appointment.ends_at > func.statement_timestamp(),
        )
        query = query.where(upcoming if period == "upcoming" else ~upcoming)
    if tenant_id is not None:
        query = query.where(Appointment.tenant_id == tenant_id)
    if status is not None:
        query = query.where(current_status == status)
    if start is not None:
        query = query.where(Appointment.starts_at >= start)
    if end is not None:
        query = query.where(Appointment.starts_at < end)
    if position is not None:
        position_key = tuple_(Appointment.starts_at, Appointment.appointment_id)
        query = query.where(
            position_key < tuple_(*position)
            if period == "past"
            else position_key > tuple_(*position)
        )
    ordering = (
        (Appointment.starts_at.desc(), Appointment.appointment_id.desc())
        if period == "past"
        else (Appointment.starts_at, Appointment.appointment_id)
    )
    rows = session.execute(query.order_by(*ordering).limit(limit + 1)).all()
    next_cursor = (
        encode_appointment_cursor(settings, scope, rows[limit - 1][0])
        if len(rows) > limit
        else None
    )
    return AppointmentPage(
        items=[appointment_public(row, status=state) for row, state in rows[:limit]],
        next_cursor=next_cursor,
    )


@router.get("/appointments/{appointment_id}", response_model=AppointmentPublic)
def appointment_detail(appointment_id: UUID, identity: Identity, session: DB):
    appointment = visible_appointment(session, appointment_id, identity)
    now = server_now(session)
    status = (
        "expired"
        if appointment.status in {"held", "pending_payment"}
        and (appointment.hold_expires_at <= now)
        else appointment.status
    )
    return appointment_public(appointment, status=status)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentPublic)
def cancel(
    appointment_id: UUID, body: Cancellation, request: Request, identity: Identity, session: DB
):
    # Conceal resource/state from unrelated callers before taking mutation locks.
    visible_appointment(session, appointment_id, identity, cancel=True)
    appointment = lock_appointment(session, appointment_id)
    if appointment.status == "cancelled":
        return appointment_public(appointment)
    cache = request.app.state.hold_cache
    expire_slot_holds(session, appointment.slot_id, server_now(session), cache)
    if appointment.status == "expired":
        # Persist expiry even when the requested cancellation can no longer proceed.
        session.commit()
        invalid_transition()
    cancel_appointment(
        appointment, server_now(session), body.reason, identity.subject_id, session=session
    )
    slot_id = appointment.slot_id
    session.commit()
    # Cleanup after commit remains safe if a replacement hold was already published.
    cache.release(slot_id, appointment_id)
    return appointment_public(appointment)


def internal_action(appointment_id, action, session):
    appointment = lock_appointment(session, appointment_id)
    consultation_action(appointment, action, server_now(session))
    session.commit()
    return appointment_public(appointment)


@router.get(
    "/internal/appointments/{appointment_id}",
    response_model=AppointmentPublic,
    dependencies=[Depends(require_consultation)],
    tags=["internal"],
)
def consultation_context(appointment_id: UUID, session: DB):
    appointment = session.get(Appointment, appointment_id)
    if appointment is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return appointment_public(appointment)


@router.post(
    "/internal/appointments/{appointment_id}/start",
    response_model=AppointmentPublic,
    dependencies=[Depends(require_consultation)],
    tags=["internal"],
)
def start(appointment_id: UUID, session: DB):
    return internal_action(appointment_id, "start", session)


@router.post(
    "/internal/appointments/{appointment_id}/complete",
    response_model=AppointmentPublic,
    dependencies=[Depends(require_consultation)],
    tags=["internal"],
)
def complete(appointment_id: UUID, session: DB):
    return internal_action(appointment_id, "complete", session)


@router.post(
    "/internal/appointments/{appointment_id}/no-show",
    response_model=AppointmentPublic,
    dependencies=[Depends(require_operator)],
    tags=["internal"],
)
def no_show(appointment_id: UUID, session: DB):
    return internal_action(appointment_id, "no-show", session)
