"""Atomically drain B03 receipts into payment truth and C05 outbox facts."""

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telelink_common.events import new_event
from telelink_common.outbox import add_event
from telelink_common.outbox.publisher import retry_delay

from app.models import (
    CheckoutAttempt,
    MedicationCheckoutAttempt,
    Payment,
    StripeWebhookEvent,
    event_outbox,
)
from app.provider import ProviderRejected, ProviderUncertain
from app.reconciliation import ReceiptDeferred, ReceiptRejected, reconcile


def payment_for_receipt(session, receipt):
    obj = receipt.object_data
    raw_id = obj.get("metadata", {}).get("payment_id")
    if raw_id is not None:
        try:
            payment_id = UUID(raw_id)
        except (ValueError, TypeError, AttributeError):
            raise ReceiptRejected("invalid_payment_id") from None
        payment = session.get(Payment, payment_id)
        if payment is None:
            raise ReceiptDeferred("payment_not_found")
        return payment
    field = (
        Payment.provider_checkout_id
        if receipt.event_type.startswith("checkout.session.")
        else Payment.provider_payment_id
    )
    return session.scalar(
        select(Payment).where(
            Payment.provider == "stripe",
            Payment.provider_account_id.is_(None),
            field == obj.get("id"),
        )
    )


def apply_receipt(session, receipt, provider, now):
    payment = payment_for_receipt(session, receipt)
    if payment is None:
        receipt.status = "ignored"  # An unrelated account event without application metadata.
        return
    # Same namespace as B02 checkout/expiry; a nonblocking transaction lock avoids
    # racing a lost create response or deadlocking while a checkout is in flight.
    acquired = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:name, 0))"),
        {"name": "billing-checkout:" + str(payment.order_id or payment.appointment_id)},
    )
    if not acquired:
        raise ReceiptDeferred("checkout_busy")
    payment = session.scalar(
        select(Payment)
        .where(Payment.payment_id == payment.payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    medication = payment.purpose == "medication_delivery"
    attempt = session.get(
        MedicationCheckoutAttempt if medication else CheckoutAttempt, payment.payment_id
    )
    if attempt is None:
        raise ReceiptDeferred("checkout_context_missing")
    outcome, intent_id = reconcile(provider, receipt, payment, attempt)
    if intent_id:
        payment.provider_payment_id = intent_id
    if outcome == "succeeded" and payment.status in {"pending", "failed"}:
        payment.status = "succeeded"
        # Expiry does not erase a paid fact. Scheduling owns late-payment recovery
        # and duplicate-charge/refund decisions after consuming this success.
        attempt.closed_at = attempt.closed_at or now
        if medication and now >= attempt.quote_expires_at:
            # Conservative: delayed processing also requires review. Never hide a
            # verified charge or imply that an expired delivery fee remains valid.
            payment.resolution = "refund_required"
            attempt.resolution_reason = "quote_expired"
            attempt.resolution_requested_at = now
        add_event(
            session,
            event_outbox,
            new_event(
                "medication_payment_succeeded.v1"
                if medication
                else "consultation_payment_succeeded.v1",
                tenant_id=payment.tenant_id,
                correlation_id=payment.payment_id,
                occurred_at=now,
                event_id=uuid5(
                    NAMESPACE_URL, f"telelink.billing:payment-success:{payment.payment_id}"
                ),
                data={
                    "payment_id": payment.payment_id,
                    ("order_id" if medication else "appointment_id"): (
                        payment.order_id if medication else payment.appointment_id
                    ),
                    "amount": {"amount_minor": payment.amount_minor, "currency": payment.currency},
                },
            ),
        )
    elif outcome == "failed" and payment.status == "pending":
        payment.status = "failed"
        attempt.closed_at = attempt.closed_at or now
    receipt.status = "processed"


def process_pending(engine, provider, *, limit=100, now=None):
    """Each receipt has one transaction; retry/rejection cannot leak partial changes."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    now = now or datetime.now(timezone.utc)
    outcomes = {"processed": 0, "ignored": 0, "rejected": 0, "deferred": 0}
    for _ in range(limit):
        with Session(engine) as session, session.begin():
            receipt = session.scalar(
                select(StripeWebhookEvent)
                .where(
                    StripeWebhookEvent.status == "pending",
                    StripeWebhookEvent.next_attempt_at <= now,
                )
                .order_by(StripeWebhookEvent.next_attempt_at, StripeWebhookEvent.received_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if receipt is None:
                break
            try:
                with session.begin_nested():
                    apply_receipt(session, receipt, provider, now)
                    receipt.processed_at = now
                    receipt.last_error = None
                    session.flush()
            except (ReceiptRejected, IntegrityError) as error:
                receipt.status = "rejected"
                receipt.last_error = (
                    str(error)
                    if isinstance(error, ReceiptRejected)
                    else "payment_integrity_conflict"
                )
                receipt.processed_at = now
            except (ReceiptDeferred, ProviderUncertain, ProviderRejected) as error:
                receipt.attempts += 1
                receipt.last_error = (
                    str(error) if isinstance(error, ReceiptDeferred) else "provider_unavailable"
                )
                receipt.next_attempt_at = now + retry_delay(receipt.attempts)
                outcomes["deferred"] += 1
                continue
            outcomes[receipt.status] += 1
    return outcomes
