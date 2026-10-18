"""C03 billing reservation, using the same slot-first locks as cancellation/expiry."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api import DB
from app.billing import BillingClient
from app.booking import appointment_public
from app.holds import expire_slot_holds, server_now
from app.models import Appointment
from app.payments import PaymentEventRejected
from app.schemas import AppointmentPublic
from app.transitions import lock_appointment

router = APIRouter(tags=["internal"])
Billing = Annotated[
    str, Depends(require_service("billing", "telelink-scheduling-billing", "billing_secret"))
]


class CheckoutReservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: UUID
    payment_id: UUID


@router.post(
    "/internal/appointments/{appointment_id}/checkout-reservation", response_model=AppointmentPublic
)
def reserve(
    appointment_id: UUID,
    body: CheckoutReservation,
    request: Request,
    caller: Billing,
    session: DB,
    response: Response,
):
    original = session.get(Appointment, appointment_id)
    if original is None or original.patient_id != body.patient_id:
        raise DomainError(404, "not_found", "Resource not found.")
    tenant = request.app.state.tenant_client
    tenant.booking_profile(original.tenant_id, request.state.request_id)
    doctors = tenant.active_doctors(original.tenant_id, request.state.request_id)
    appointment = lock_appointment(session, appointment_id)
    expire_slot_holds(
        session, appointment.slot_id, server_now(session), request.app.state.hold_cache
    )
    if appointment.status == "expired":
        session.commit()
        raise DomainError(409, "hold_expired", "The booking hold has expired.")
    if appointment.status in {"confirmed", "in_progress", "completed", "no_show"}:
        raise DomainError(409, "already_paid", "Appointment is already paid.")
    if (
        appointment.status not in {"held", "pending_payment"}
        or appointment.doctor_id not in doctors
    ):
        raise DomainError(
            409, "invalid_appointment_transition", "Appointment cannot accept checkout."
        )
    if appointment.payment_id not in {None, body.payment_id}:
        # Independently verify failure; never trust a caller-supplied previous-failed flag.
        client = None
        try:
            client = BillingClient(request.app.state.settings)
            previous = client.payment(appointment.payment_id)
        except (PaymentEventRejected, ValueError):
            raise DomainError(
                503, "unavailable", "Previous payment verification unavailable."
            ) from None
        finally:
            if client is not None:
                client.close()
        if (
            previous.payment_id != appointment.payment_id
            or previous.appointment_id != appointment.appointment_id
            or previous.patient_id != appointment.patient_id
            or previous.tenant_id != appointment.tenant_id
            or previous.purpose != "consultation"
            or previous.status != "failed"
        ):
            raise DomainError(409, "payment_attempt_pending", "Previous payment is not failed.")
    # Remote verification may take time; equality at the original deadline is expired.
    if server_now(session) >= appointment.hold_expires_at:
        expire_slot_holds(
            session, appointment.slot_id, server_now(session), request.app.state.hold_cache
        )
        session.commit()
        raise DomainError(409, "hold_expired", "The booking hold has expired.")
    appointment.payment_id = body.payment_id
    appointment.status = "pending_payment"
    appointment.payment_resolution = "awaiting_payment"
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return appointment_public(appointment)
