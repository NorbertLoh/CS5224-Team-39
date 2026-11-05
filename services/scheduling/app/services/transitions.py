"""S04 transitions; all callers lock slot before appointment and use server time."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.models import Appointment, AvailabilitySlot, event_outbox


def invalid_transition():
    raise DomainError(
        409, "invalid_appointment_transition", "Appointment cannot perform this action."
    )


def lock_appointment(session, appointment_id):
    slot_id = session.scalar(
        select(Appointment.slot_id).where(Appointment.appointment_id == appointment_id)
    )
    if slot_id is None:
        raise DomainError(404, "not_found", "Resource not found.")
    session.scalar(
        select(AvailabilitySlot).where(AvailabilitySlot.slot_id == slot_id).with_for_update()
    )
    appointment = session.scalar(
        select(Appointment)
        .where(Appointment.appointment_id == appointment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if appointment is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return appointment


def cancel_appointment(appointment, now, reason, actor_id, *, session):
    if appointment.status == "cancelled":
        return False
    if appointment.status not in {"held", "pending_payment", "confirmed"}:
        invalid_transition()
    if appointment.status == "confirmed" and now >= appointment.starts_at:
        invalid_transition()
    if (appointment.status == "confirmed" or appointment.payment_resolution == "confirmed") and (
        appointment.payment_resolution != "refunded"
    ):
        appointment.payment_resolution = "refund_required"
        if appointment.payment_id is not None:
            # Local import keeps the shared slot-lock helpers independent of the consumer.
            from app.services.payments import recovery_record

            recovery_record(
                session, appointment, appointment.payment_id, "appointment_cancelled", now
            )
    appointment.status = "cancelled"
    appointment.cancellation_reason = reason
    appointment.cancelled_by_subject_id = actor_id
    appointment.cancelled_at = now
    add_event(
        session,
        event_outbox,
        new_event(
            "appointment_cancelled.v1",
            tenant_id=appointment.tenant_id,
            correlation_id=appointment.appointment_id,
            occurred_at=now,
            event_id=uuid5(
                NAMESPACE_URL, f"telelink:appointment-cancelled:{appointment.appointment_id}"
            ),
            data={"appointment_id": appointment.appointment_id},
        ),
    )
    return True


def consultation_action(appointment, action, now, *, early_minutes=0):
    if action == "start":
        if appointment.status != "confirmed":
            invalid_transition()
        appointment.status = "in_progress"
    elif action == "complete":
        if appointment.status != "in_progress":
            invalid_transition()
        appointment.status = "completed"
    elif action == "no-show":
        if appointment.status != "confirmed" or now < appointment.ends_at:
            invalid_transition()
        appointment.status = "no_show"
    else:
        invalid_transition()
