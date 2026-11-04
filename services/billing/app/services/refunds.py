from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError
from telelink_common.outbox.publisher import retry_delay

from app.integrations.stripe import ProviderRejected, ProviderUncertain
from app.integrations.stripe_refunds import reconcile_refund
from app.models import Payment, RefundAttempt
from app.services.reconciliation import ReceiptRejected


def process_refunds(engine, provider, sources, *, limit=20, now=None):
    now = now or datetime.now(timezone.utc)
    counts = {"processed": 0, "deferred": 0}
    with Session(engine) as session:
        ids = session.scalars(
            select(RefundAttempt.refund_id)
            .where(
                RefundAttempt.next_attempt_at <= now,
                (RefundAttempt.status == "pending")
                | ((RefundAttempt.status == "succeeded") & RefundAttempt.synced_at.is_(None)),
            )
            .order_by(RefundAttempt.next_attempt_at)
            .limit(limit)
        ).all()
    for refund_id in ids:
        with Session(engine) as session, session.begin():
            # All writers lock payment before refund; concurrent workers skip busy payments.
            payment_id = session.scalar(
                select(RefundAttempt.payment_id).where(RefundAttempt.refund_id == refund_id)
            )
            payment = session.scalar(
                select(Payment)
                .where(Payment.payment_id == payment_id)
                .with_for_update(skip_locked=True)
            )
            if payment is None:
                continue
            attempt = session.get(RefundAttempt, refund_id)
            if attempt.next_attempt_at > now or attempt.status not in {"pending", "succeeded"}:
                continue
            try:
                already_succeeded = attempt.status == "succeeded"
                if attempt.status == "pending":
                    outcome, provider_id = reconcile_refund(provider, payment, attempt, now)
                    attempt.provider_refund_id = provider_id
                    if outcome in {"failed", "canceled"}:
                        attempt.status = "failed"
                        attempt.last_error = "provider_failed"
                        payment.status = "refund_failed"
                    elif outcome == "succeeded":
                        attempt.status = "succeeded"
                        attempt.last_error = None
                        payment.status = "refunded"
                        payment.resolution = "none"
                    else:
                        attempt.last_error = None
                # Commit provider success before scheduling independently reads billing.
                if already_succeeded and attempt.synced_at is None:
                    sources.complete_refund(payment, str(refund_id))
                    attempt.synced_at = now
                    attempt.last_error = None
            except (ProviderUncertain, DomainError):
                attempt.last_error = "verification_pending"
                counts["deferred"] += 1
            except (ProviderRejected, ReceiptRejected):
                # Do not automatically recreate a rejected or mismatched operation.
                attempt.status = "review"
                attempt.last_error = "support_review_required"
                payment.status = "refund_failed"
            attempt.attempts += 1
            attempt.next_attempt_at = now + (
                timedelta(seconds=30)
                if attempt.status == "succeeded"
                else retry_delay(attempt.attempts)
            )
            attempt.updated_at = now
            counts["processed"] += 1
    return counts
