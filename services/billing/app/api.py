from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_global_role
from telelink_common.errors import DomainError, ErrorEnvelope
from telelink_common.service_auth import require_service

from app.checkout import create_checkout
from app.database import get_session
from app.models import Payment
from app.schemas import CheckoutCreate, CheckoutPublic, PaymentPublic, payment_public

router = APIRouter(
    responses={s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 422, 502, 503)}
)
Patient = Annotated[CurrentIdentity, Depends(require_global_role("patient"))]
Scheduling = Annotated[
    str, Depends(require_service("scheduling", "telelink-billing-scheduling", "scheduling_secret"))
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
def scheduling_payment(
    payment_id: UUID, caller: Scheduling, session: Annotated[Session, Depends(get_session)]
):
    payment = session.get(Payment, payment_id)
    if payment is None or payment.purpose != "consultation":
        raise DomainError(404, "not_found", "Resource not found.")
    return payment_public(payment)
