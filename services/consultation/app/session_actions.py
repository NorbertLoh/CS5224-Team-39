"""Doctor-driven lifecycle with retryable scheduling handoff."""

from telelink_common.errors import DomainError

from app.admissions import CONTEXT_FIELDS
from app.lifecycle import ensure_session, transition
from app.upstream import Appointment


def act(db, sources, appointment_id, identity, request_id, action):
    appointment = sources.appointment(appointment_id, request_id)
    if appointment.doctor_id != identity.subject_id:
        raise DomainError(404, "not_found", "Resource not found.")
    statuses = {"confirmed", "in_progress"} if action == "start" else {"in_progress", "completed"}
    sources.validate(appointment, identity.subject_id, request_id, statuses=statuses)
    record = ensure_session(db, **{key: getattr(appointment, key) for key in CONTEXT_FIELDS})
    current = sources.appointment(appointment_id, request_id)
    if any(getattr(current, key) != getattr(record, key) for key in CONTEXT_FIELDS):
        raise DomainError(409, "session_context_conflict", "Session context has changed.")
    sources.validate(current, identity.subject_id, request_id, statuses=statuses)
    transition(
        db,
        session_id=record.session_id,
        tenant_id=record.tenant_id,
        doctor_id=identity.subject_id,
        action="start" if action == "start" else "end",
    )
    target = "in_progress" if action == "start" else "completed"
    # Persist the authorised local intent before contacting scheduling. If the
    # remote response is lost, retry reads its current state and skips an already
    # applied transition. A completed local session denies new admissions even
    # while a scheduling handoff is unavailable. No distributed atomicity implied.
    db.commit()
    if current.status != target:
        result = sources.call(
            "scheduling",
            f"/internal/appointments/{appointment_id}/{action}",
            Appointment,
            request_id,
            {},
        )
        if result.status != target or any(
            getattr(result, field) != getattr(record, field) for field in CONTEXT_FIELDS
        ):
            raise DomainError(502, "upstream_error", "Invalid upstream appointment.")
    return {"appointment_id": record.appointment_id, "status": target}
