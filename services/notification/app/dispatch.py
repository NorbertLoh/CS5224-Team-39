"""Claim once, send outside DB transactions, and hold ambiguous outcomes for review."""

from datetime import timedelta

from sqlalchemy import func, select, update

from app.email import EmailSendError
from app.models import NotificationJob
from app.templates import render_email


def recover_stale(sessions, settings):
    with sessions.begin() as session:
        cutoff = session.scalar(select(func.now())) - timedelta(seconds=settings.stale_seconds)
        result = session.execute(
            update(NotificationJob)
            .where(NotificationJob.status == "sending", NotificationJob.send_started_at < cutoff)
            .values(status="uncertain", ready_at=None, error_code="ses_unconfirmed")
        )
        return result.rowcount


def dispatch_one(sessions, sender, settings):
    with sessions.begin() as session:
        job = session.scalar(
            select(NotificationJob)
            .where(
                NotificationJob.status.in_(["pending", "failed"]),
                NotificationJob.ready_at <= func.now(),
                NotificationJob.attempts < settings.send_max_attempts,
            )
            .order_by(NotificationJob.ready_at, NotificationJob.job_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        # Render before committing a claim; invalid configuration cannot create an uncertain send.
        message = render_email(job.template, settings.app_url)
        job.status, job.ready_at, job.error_code = "sending", None, None
        job.attempts += 1
        job.send_started_at = session.scalar(select(func.now()))
        job_id, recipient, attempt = job.job_id, job.recipient_email, job.attempts
    # A crash from here onward leaves sending, which expires into uncertain, never auto-resends.
    try:
        message_id = sender.send(recipient, message)
        status, error_code, retry = "sent", None, False
    except EmailSendError as error:
        status = "failed" if error.definitive else "uncertain"
        error_code = "ses_rejected" if error.definitive else "ses_unconfirmed"
        retry = error.definitive and error.retryable and attempt < settings.send_max_attempts
        message_id = None
    except Exception:
        status, error_code, retry, message_id = "uncertain", "ses_unconfirmed", False, None
    with sessions.begin() as session:
        job = session.get(NotificationJob, job_id, with_for_update=True)
        # Stale recovery may already have marked the claim uncertain while SES was responding.
        if job.status not in {"sending", "uncertain"} or job.attempts != attempt:
            raise RuntimeError("Notification send claim changed")
        now = session.scalar(select(func.now()))
        job.status, job.error_code = status, error_code
        job.provider_message_id = message_id
        job.sent_at = now if status == "sent" else None
        job.ready_at = now + timedelta(seconds=settings.retry_seconds) if retry else None
    return True
