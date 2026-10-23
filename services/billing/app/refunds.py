"""Clinic-owned full consultation refunds, persisted before provider side effects."""

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, has_tenant_role, require_identity
from telelink_common.errors import DomainError
from telelink_common.outbox.publisher import retry_delay

from app.database import get_session
from app.models import Payment, RefundAttempt
from app.provider import ProviderRejected, ProviderUncertain
from app.queries import access_scope
from app.reconciliation import ReceiptRejected
from app.refund_provider import reconcile_refund

router = APIRouter(tags=["refunds"])
Identity = Annotated[CurrentIdentity, Depends(require_identity)]
Database = Annotated[Session, Depends(get_session)]


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("A refund reason is required")
        return value


class RefundPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    refund_id: UUID
    payment_id: UUID
    requested_by: UUID
    requested_by_name: str
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_error: str | None
    retry_allowed: bool = False


def public(attempt):
    return RefundPublic.model_validate(attempt).model_copy(
        update={
            "retry_allowed": attempt.status == "failed" and attempt.last_error == "provider_failed"
        }
    )


@router.get("/payments/{payment_id}/refunds", response_model=list[RefundPublic])
def refund_history(payment_id: UUID, identity: Identity, session: Database):
    predicate, _ = access_scope(identity, conceal=True)
    if session.scalar(select(Payment).where(predicate, Payment.payment_id == payment_id)) is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return [
        public(a)
        for a in session.scalars(
            select(RefundAttempt)
            .where(RefundAttempt.payment_id == payment_id)
            .order_by(RefundAttempt.created_at.desc(), RefundAttempt.refund_id.desc())
        )
    ]


@router.post("/payments/{payment_id}/refunds", response_model=RefundPublic, status_code=202)
def request_refund(
    payment_id: UUID, body: RefundCreate, request: Request, identity: Identity, session: Database
):
    # Platform and patient visibility do not grant refund authority.
    payment = session.get(Payment, payment_id)
    if payment is None or not any(
        has_tenant_role(m, payment.tenant_id, "clinic_admin") for m in identity.memberships
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    payment = session.scalar(
        select(Payment)
        .where(Payment.payment_id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    latest = session.scalar(
        select(RefundAttempt)
        .where(RefundAttempt.payment_id == payment_id)
        .order_by(RefundAttempt.created_at.desc())
        .limit(1)
    )
    if latest and not (latest.status == "failed" and latest.last_error == "provider_failed"):
        return public(latest)
    if (
        payment.purpose != "consultation"
        or payment.provider != "stripe"
        or payment.provider_account_id is not None
        or not payment.provider_payment_id
        or payment.amount_minor <= 0
        or payment.status not in {"succeeded", "refund_failed"}
    ):
        raise DomainError(
            409, "refund_not_available", "Only paid Stripe consultations can be refunded."
        )
    request.app.state.sources.prepare_refund(payment, request.state.request_id)
    attempt = RefundAttempt(
        payment_id=payment_id,
        requested_by=identity.subject_id,
        requested_by_name=identity.display_name,
        reason=body.reason,
    )
    session.add(attempt)
    payment.status = "refund_pending"
    payment.resolution = "refund_required"
    session.commit()
    session.refresh(attempt)
    return public(attempt)


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
