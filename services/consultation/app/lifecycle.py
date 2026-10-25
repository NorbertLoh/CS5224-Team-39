"""Internal domain operations. The caller owns the transaction and trusted context.

No method here authorizes HTTP callers or establishes appointment/payment truth.
V02 must validate those before calling, and coordinate scheduling start/complete.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from telelink_common.errors import DomainError

from app.models import ConsultationSession

JOIN_EARLY = timedelta(minutes=10)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Session timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def server_time(now: datetime | None) -> datetime:
    # Explicit injection is for trusted callers/tests, never browser input.
    return utc(now if now is not None else datetime.now(timezone.utc))


def ensure_session(
    db,
    *,
    appointment_id: UUID,
    tenant_id: UUID,
    patient_id: UUID,
    doctor_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
):
    """Idempotently persist a trusted immutable appointment snapshot.

    The appointment uniqueness constraint serializes concurrent creation. A
    conflicting context must never return another tenant's existing session.
    """
    fields = dict(
        appointment_id=appointment_id,
        tenant_id=tenant_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        starts_at=utc(starts_at),
        ends_at=utc(ends_at),
    )
    if fields["starts_at"] >= fields["ends_at"] or patient_id == doctor_id:
        raise ValueError("Invalid appointment schedule or participants")
    db.execute(
        insert(ConsultationSession)
        .values(**fields)
        .on_conflict_do_nothing(index_elements=["appointment_id"])
    )
    record = db.scalar(
        select(ConsultationSession)
        .where(ConsultationSession.appointment_id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if any(getattr(record, key) != value for key, value in fields.items()):
        raise DomainError(409, "session_context_conflict", "Session context has changed.")
    return record


def locked_session(db, *, session_id: UUID, tenant_id: UUID):
    record = db.scalar(
        select(ConsultationSession)
        .where(
            ConsultationSession.session_id == session_id,
            ConsultationSession.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return record


def can_join(record: ConsultationSession, *, now: datetime | None = None) -> bool:
    """Window eligibility only, never an admission/authorization decision."""
    instant = server_time(now)
    opens_at = utc(record.starts_at) - JOIN_EARLY
    return opens_at <= instant and (
        record.status == "in_progress"
        or (record.status == "scheduled" and instant < utc(record.ends_at))
    )


def transition(
    db,
    *,
    session_id: UUID,
    tenant_id: UUID,
    doctor_id: UUID,
    action: str,
    now: datetime | None = None,
):
    """Lock and apply doctor-driven start/end; retries preserve original times."""
    record = locked_session(db, session_id=session_id, tenant_id=tenant_id)
    if record.doctor_id != doctor_id:
        raise DomainError(403, "forbidden", "Assigned doctor is required.")
    instant = server_time(now)
    if action == "start":
        if record.status == "in_progress":
            return record
        if record.status != "scheduled" or not record.starts_at <= instant < record.ends_at:
            raise DomainError(409, "invalid_session_transition", "Session cannot start.")
        record.status, record.started_at = "in_progress", instant
    elif action == "end":
        if record.status == "completed":
            return record
        if record.status != "in_progress" or instant < record.started_at:
            raise DomainError(409, "invalid_session_transition", "Session cannot end.")
        record.status, record.ended_at = "completed", instant
    else:
        raise ValueError("Unknown session action")
    db.flush()
    return record
