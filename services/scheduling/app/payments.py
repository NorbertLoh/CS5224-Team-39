"""On-time success handling; inbox, appointment and confirmation outbox commit together."""

from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.holds import server_now
from app.models import event_outbox
from app.transitions import lock_appointment


class PaymentEventRejected(Exception):
    """Safe errors only: queue retries/DLQ retain the event for investigation or S06."""


def confirm_payment(session, event, billing):
    if event.detail_type != "consultation_payment_succeeded.v1":
        raise PaymentEventRejected("Unexpected payment event type")
    # Network lookup before reservation locks. Billing owns immutable succeeded facts.
    payment = billing.payment(event.data.payment_id)
    appointment = lock_appointment(session, event.data.appointment_id)
    if (
        event.tenant_id != appointment.tenant_id
        or event.data.payment_id != appointment.payment_id
        or event.data.amount.amount_minor != appointment.consultation_price_minor
        or event.data.amount.currency != appointment.currency
        or payment.payment_id != event.data.payment_id
        or payment.appointment_id != appointment.appointment_id
        or payment.tenant_id != appointment.tenant_id
        or payment.patient_id != appointment.patient_id
        or payment.purpose != "consultation"
        or payment.status != "succeeded"
        or payment.amount != event.data.amount
    ):
        raise PaymentEventRejected("Payment context does not match appointment")
    # A second event ID for the same charge must not emit a second confirmation.
    if appointment.status in {"confirmed", "in_progress", "completed", "no_show"}:
        if appointment.payment_resolution != "confirmed":
            raise PaymentEventRejected("Payment resolution requires review")
        return
    now = server_now(session)  # after lock wait, never use the producer timestamp
    if (
        appointment.status != "pending_payment"
        or appointment.hold_expires_at is None
        or now >= appointment.hold_expires_at
    ):
        raise PaymentEventRejected("Payment requires S06 recovery")
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
            occurred_at=now,
            data={"appointment_id": appointment.appointment_id},
        ),
    )
