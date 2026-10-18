from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_global_role
from telelink_common.errors import DomainError, ErrorEnvelope
from telelink_common.service_auth import bearer, require_service

from app.checkout import create_checkout, now
from app.database import get_session
from app.medication_checkout import create_medication_checkout
from app.models import MedicationCheckoutAttempt, Payment
from app.schemas import (
    CheckoutCreate,
    CheckoutPublic,
    MedicationCheckoutCreate,
    MedicationResolution,
    PaymentPublic,
    payment_public,
)

router = APIRouter(
    responses={s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 422, 502, 503)}
)
Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]


def payment_reader(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    for caller in ("scheduling", "fulfilment", "consultation"):
        if getattr(request.app.state.settings, caller + "_secret") is None:
            continue
        try:
            return require_service(caller, "telelink-billing-" + caller, caller + "_secret")(
                request, credentials
            )
        except HTTPException as error:
            if error.status_code != 401:
                raise
    raise HTTPException(401, "Service credential required", headers={"WWW-Authenticate": "Bearer"})


PaymentReader = Annotated[str, Depends(payment_reader)]
Fulfilment = Annotated[
    str, Depends(require_service("fulfilment", "telelink-billing-fulfilment", "fulfilment_secret"))
]


@router.post(
    "/consultation-checkouts",
    response_model=CheckoutPublic,
    status_code=201,
    responses={200: {"model": CheckoutPublic}},
)
def consultation_checkout(
    body: CheckoutCreate,
    request: Request,
    response: Response,
    identity: Patient,
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
    ],
):
    state = request.app.state
    if state.database_engine is None:
        raise DomainError(503, "unavailable", "Billing storage is not configured.")
    result, replay = create_checkout(
        state.database_engine,
        state.sources,
        state.provider,
        state.settings,
        identity.subject_id,
        body.appointment_id,
        key,
        request.state.request_id,
    )
    response.status_code = 200 if replay else 201
    return result


@router.get("/internal/payments/{payment_id}", response_model=PaymentPublic, tags=["internal"])
def internal_payment(
    payment_id: UUID, caller: PaymentReader, session: Annotated[Session, Depends(get_session)]
):
    payment = session.get(Payment, payment_id)
    purpose = "consultation" if caller in {"scheduling", "consultation"} else "medication_delivery"
    if payment is None or payment.purpose != purpose:
        raise DomainError(404, "not_found", "Resource not found.")
    return payment_public(payment)


@router.post(
    "/medication-checkouts",
    response_model=CheckoutPublic,
    status_code=201,
    responses={200: {"model": CheckoutPublic}},
)
def medication_checkout(
    body: MedicationCheckoutCreate,
    request: Request,
    response: Response,
    identity: Patient,
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
    ],
):
    state = request.app.state
    if state.database_engine is None:
        raise DomainError(503, "unavailable", "Billing storage is not configured.")
    result, replay = create_medication_checkout(
        state.database_engine,
        state.sources,
        state.provider,
        state.settings,
        identity.subject_id,
        body.order_id,
        body.quote_id,
        key,
        request.state.request_id,
    )
    response.status_code = 200 if replay else 201
    return result


@router.post(
    "/internal/payments/{payment_id}/resolution", response_model=PaymentPublic, tags=["internal"]
)
def medication_resolution(
    payment_id: UUID,
    body: MedicationResolution,
    caller: Fulfilment,
    session: Annotated[Session, Depends(get_session)],
):
    payment = session.scalar(
        select(Payment).where(Payment.payment_id == payment_id).with_for_update()
    )
    if (
        payment is None
        or payment.purpose != "medication_delivery"
        or payment.order_id != body.resource_id
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    attempt = session.get(MedicationCheckoutAttempt, payment_id)
    if (
        attempt is None
        or not attempt.reservation
        or attempt.reservation.get("tenant_id") != str(payment.tenant_id)
    ):
        raise DomainError(409, "payment_context_mismatch", "Payment context cannot be verified.")
    if payment.status not in {"succeeded", "refund_pending", "refund_failed"}:
        raise DomainError(
            409, "invalid_payment_transition", "A committed successful charge is required."
        )
    payment.resolution = "refund_required"
    if attempt.resolution_reason is None:
        attempt.resolution_reason = body.reason
        attempt.resolution_requested_at = now()
    session.commit()
    return payment_public(payment)
