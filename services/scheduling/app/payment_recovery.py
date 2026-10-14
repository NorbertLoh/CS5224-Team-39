"""Retry committed refund exceptions without tying payment queue delivery to billing writes."""

import logging

from sqlalchemy import select

from app.holds import server_now
from app.models import Appointment, PaymentRecovery
from app.payments import PaymentEventRejected

logger = logging.getLogger("telelink.scheduling.payment_recovery")


def deliver_resolutions(sessions, billing, *, limit=20):
    delivered, failed = 0, 0
    with sessions() as session:
        ids = session.scalars(
            select(PaymentRecovery.payment_id)
            .where(
                PaymentRecovery.outcome == "refund_required", PaymentRecovery.delivered_at.is_(None)
            )
            .order_by(
                PaymentRecovery.last_attempt_at.asc().nulls_first(), PaymentRecovery.payment_id
            )
            .limit(limit)
        ).all()
    for payment_id in ids:
        # Database errors propagate. A crash after remote success requires a safe replay.
        with sessions.begin() as session:
            recovery = session.scalar(
                select(PaymentRecovery)
                .where(
                    PaymentRecovery.payment_id == payment_id, PaymentRecovery.delivered_at.is_(None)
                )
                .with_for_update(skip_locked=True)
            )
            if recovery is None:
                continue
            recovery.last_attempt_at = server_now(session)
            try:
                payment = billing.refund_required(recovery)
                appointment = session.get(Appointment, recovery.appointment_id)
                if (
                    appointment is None
                    or payment.patient_id != appointment.patient_id
                    or payment.amount.amount_minor != appointment.consultation_price_minor
                    or payment.amount.currency != appointment.currency
                ):
                    raise PaymentEventRejected("Billing resolution context mismatch")
            except PaymentEventRejected:
                failed += 1
                logger.warning("billing_resolution_delivery_unavailable")
            else:
                recovery.delivered_at = server_now(session)
                delivered += 1
    return {"delivered": delivered, "failed": failed}
