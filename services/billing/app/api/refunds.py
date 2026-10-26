"""Clinic-owned full consultation refunds, persisted before provider side effects."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError

from app.api.dependencies import Database, Identity
from app.models import Payment, RefundAttempt
from app.services.queries import access_scope
from app.services.refund_policy import refund_availability

router = APIRouter(tags=["refunds"])


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
    availability = refund_availability(payment)
    if availability == "demo_payment":
        raise DomainError(
            409, "refund_demo_payment", "This is a demo payment. No actual charge was made."
        )
    if availability != "available":
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
