"""Persistent grant rotation, pre-registration consumption and active lease checks."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from telelink_common.errors import DomainError

from app.lifecycle import can_join, ensure_session, locked_session
from app.models import Admission, ConsultationSession

CONTEXT_FIELDS = ("appointment_id", "tenant_id", "patient_id", "doctor_id", "starts_at", "ends_at")


def now():
    return datetime.now(timezone.utc)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def denied():
    raise DomainError(403, "admission_denied", "Admission is invalid or no longer permitted.")


def lease_public(lease, record):
    return dict(
        session_id=record.session_id,
        tenant_id=record.tenant_id,
        appointment_id=record.appointment_id,
        subject_id=lease.subject_id,
        peer_id=lease.peer_id,
        expires_at=lease.expires_at,
    )


def issue(db, sources, settings, appointment_id, identity, request_id):
    appointment = sources.appointment(appointment_id, request_id)
    # Authorize before taking locks or persisting any snapshot.
    sources.validate(appointment, identity.subject_id, request_id)
    record = ensure_session(db, **{key: getattr(appointment, key) for key in CONTEXT_FIELDS})
    # A competing consume/issue may have held the session lock during the first
    # lookup. Re-read current remote context after acquiring the lock.
    current = sources.appointment(appointment_id, request_id)
    if any(getattr(current, key) != getattr(record, key) for key in CONTEXT_FIELDS):
        denied()
    sources.validate(current, identity.subject_id, request_id)
    instant = now()
    if not can_join(record, now=instant, early_minutes=settings.test_join_early_minutes):
        denied()
    lease = db.get(Admission, (record.session_id, identity.subject_id), populate_existing=True)
    if (
        lease is not None
        and lease.consumed_at is not None
        and lease.released_at is None
        and instant < lease.expires_at
    ):
        raise DomainError(
            409, "participant_connected", "Participant already has an active admission."
        )
    if lease is None:
        lease = Admission(
            session_id=record.session_id, tenant_id=record.tenant_id, subject_id=identity.subject_id
        )
        db.add(lease)
    token = secrets.token_urlsafe(32)
    lease.token_digest, lease.peer_id = digest(token), uuid4()
    lease.issued_at = instant
    lease.expires_at = min(
        instant + timedelta(seconds=settings.admission_ttl_seconds), record.ends_at
    )
    lease.consumed_at = lease.released_at = None
    db.flush()
    return {**lease_public(lease, record), "token": token}


def bound_lease(db, token, peer_id):
    token_digest = digest(token)
    # Read parent ID first, then serialize all operations on the parent session.
    session_id = db.scalar(
        select(Admission.session_id).where(Admission.token_digest == token_digest)
    )
    if session_id is None:
        denied()
    record = db.scalar(
        select(ConsultationSession).where(ConsultationSession.session_id == session_id)
    )
    if record is None:
        denied()
    record = locked_session(db, session_id=session_id, tenant_id=record.tenant_id)
    lease = db.scalar(
        select(Admission)
        .where(Admission.token_digest == token_digest)
        .execution_options(populate_existing=True)
    )
    if lease is None or lease.peer_id != peer_id:
        denied()
    return record, lease


def validate_live(db, sources, record, lease, request_id):
    appointment = sources.appointment(record.appointment_id, request_id)
    if any(getattr(appointment, key) != getattr(record, key) for key in CONTEXT_FIELDS):
        denied()
    sources.validate(appointment, lease.subject_id, request_id)
    instant = now()  # Read after slow upstream calls, never extend expiry during a lookup.
    if (
        lease.released_at is not None
        or not lease.issued_at <= instant < lease.expires_at
        or not can_join(record, now=instant, early_minutes=sources.settings.test_join_early_minutes)
    ):
        denied()
    return instant


def consume(db, sources, token, peer_id, request_id, *, check=False):
    record, lease = bound_lease(db, token, peer_id)
    if (check and lease.consumed_at is None) or (not check and lease.consumed_at is not None):
        denied()
    instant = validate_live(db, sources, record, lease, request_id)
    if not check:
        lease.consumed_at = instant
        db.flush()
    return lease_public(lease, record)


def release(db, token, peer_id):
    _, lease = bound_lease(db, token, peer_id)
    if lease.consumed_at is None:
        denied()
    if lease.released_at is None:
        lease.released_at = max(now(), lease.consumed_at)
        db.flush()
