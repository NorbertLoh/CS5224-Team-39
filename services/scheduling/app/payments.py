"""Verified payment decisions commit with inbox, recovery audit and confirmation outbox."""

from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.holds import expire_slot_holds, server_now
from app.models import (
    ACTIVE_RESERVATION_STATES,
    Appointment,
    AvailabilitySlot,
    PaymentRecovery,
    event_outbox,
)
from app.transitions import lock_appointment

PAID_STATES = {"confirmed", "in_progress", "completed", "no_show"}


class PaymentEventRejected(Exception):
    """Safe errors only: unverifiable facts retry without acknowledging the event."""


def recovery_record(session, appointment, payment_id, reason, now, *, event_id=None):
    record = session.get(PaymentRecovery, payment_id)
    if record is None:
        record = PaymentRecovery(
            payment_id=payment_id,
            appointment_id=appointment.appointment_id,
            tenant_id=appointment.tenant_id,
            event_id=event_id,
            outcome="recovered" if reason == "late_payment" else "refund_required",
            reason=reason,
            previous_status=appointment.status,
            hold_expires_at=appointment.hold_expires_at,
            created_at=now,
            recovered_at=now if reason == "late_payment" else None,
        )
        session.add(record)
    elif reason == "appointment_cancelled" and record.outcome == "recovered":
        record.outcome = "refund_required"
        record.reason = reason
        record.delivered_at = None
    return record


def late_payment_reason(session, appointment, now, tenant, request_id):
    slot = session.get(AvailabilitySlot, appointment.slot_id)
    if slot.withdrawn_at is not None or appointment.starts_at <= now:
        return "appointment_unavailable"
    occupied = session.scalar(
        select(Appointment.appointment_id).where(
            Appointment.slot_id == appointment.slot_id,
            Appointment.status.in_(ACTIVE_RESERVATION_STATES),
        )
    )
    if occupied is not None:
        return "slot_reallocated"
    if tenant is None:
        raise PaymentEventRejected("Recovery eligibility verification unavailable")
    try:
        tenant.booking_profile(appointment.tenant_id, request_id)
        doctors = tenant.active_doctors(appointment.tenant_id, request_id)
    except DomainError as error:
        if error.status_code in {404, 409}:
            return "appointment_unavailable"
        raise PaymentEventRejected("Recovery eligibility verification unavailable") from None
    if appointment.doctor_id not in doctors or appointment.starts_at <= server_now(session):
        return "appointment_unavailable"
    return None


def confirm_payment(session, event, billing, tenant=None):
    if event.detail_type != "consultation_payment_succeeded.v1":
        raise PaymentEventRejected("Unexpected payment event type")
    payment = billing.payment(event.data.payment_id)
    appointment = lock_appointment(session, event.data.appointment_id)
    if (
        event.tenant_id != appointment.tenant_id
        or event.data.amount.amount_minor != appointment.consultation_price_minor
        or event.data.amount.currency != appointment.currency
        or payment.payment_id != event.data.payment_id
        or payment.appointment_id != appointment.appointment_id
        or payment.tenant_id != appointment.tenant_id
        or payment.patient_id != appointment.patient_id
        or payment.purpose != "consultation"
        or payment.status != "succeeded"
        or payment.amount != event.data.amount
        or appointment.payment_id is None
        or appointment.status == "held"
    ):
        raise PaymentEventRejected("Payment context does not match appointment")
    if session.get(PaymentRecovery, payment.payment_id) is not None:
        return
    same_payment = payment.payment_id == appointment.payment_id
    if appointment.status in PAID_STATES and same_payment:
        if appointment.payment_resolution != "confirmed":
            raise PaymentEventRejected("Payment resolution requires review")
        return
    if same_payment and appointment.payment_resolution == "refunded":
        return
    now = server_now(session)
    reason = None
    if appointment.status in PAID_STATES or (
        not same_payment
        and appointment.payment_resolution in {"confirmed", "refund_required", "refunded"}
    ):
        reason = "duplicate_charge"
    elif appointment.status == "cancelled":
        reason = "appointment_cancelled"
    elif appointment.payment_resolution in {"refund_required", "refunded"}:
        return
    late = appointment.status == "expired" or (
        appointment.hold_expires_at is not None and now >= appointment.hold_expires_at
    )
    if reason is None and late:
        previous_status = appointment.status
        expire_slot_holds(session, appointment.slot_id, now)
        reason = late_payment_reason(session, appointment, now, tenant, str(event.event_id))
        if reason is None:
            audit = recovery_record(
                session,
                appointment,
                payment.payment_id,
                "late_payment",
                now,
                event_id=event.event_id,
            )
            audit.previous_status = previous_status
    if reason is not None:
        recovery_record(
            session, appointment, payment.payment_id, reason, now, event_id=event.event_id
        )
        if reason != "duplicate_charge":
            appointment.payment_id = payment.payment_id
            appointment.payment_resolution = "refund_required"
        return
    if appointment.status not in {"pending_payment", "expired"}:
        raise PaymentEventRejected("Appointment cannot accept payment")
    appointment.payment_id = payment.payment_id
    appointment.status = "confirmed"
    appointment.payment_resolution = "confirmed"
    appointment.hold_expires_at = None
    add_event(
        session,
        event_outbox,
        new_event(
            "appointment_confirmed.v1",
            tenant_id=appointment.tenant_id,
            correlation_id=event.correlation_id,
            occurred_at=server_now(session),
            data={"appointment_id": appointment.appointment_id},
        ),
    )
