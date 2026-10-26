"""Reserve a prescription for correction before any checkout or preparation."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select
from telelink_common.errors import DomainError

from app.access import require_clinic
from app.catalogue import DB, Identity
from app.models import Order, PrescriptionCorrectionHold
from app.orders import lock
from app.schemas import StrictModel

router = APIRouter(tags=["prescription-corrections"])


class CorrectionContext(StrictModel):
    patient_id: UUID


@router.post("/clinics/{tenant_id}/prescriptions/{prescription_id}/prepare-correction")
def prepare_correction(
    tenant_id: UUID,
    prescription_id: UUID,
    body: CorrectionContext,
    request: Request,
    identity: Identity,
    session: DB,
):
    require_clinic(identity, tenant_id, {"clinic_admin"})
    lock(session, f"orders:prescription:{prescription_id}")
    hold = session.get(PrescriptionCorrectionHold, prescription_id)
    if hold is not None:
        if (hold.tenant_id, hold.patient_id) != (tenant_id, body.patient_id):
            raise DomainError(404, "not_found", "Resource not found.")
        return {
            "tenant_id": tenant_id,
            "prescription_id": prescription_id,
            "patient_id": body.patient_id,
        }
    context = request.app.state.dispensing.get(
        prescription_id, body.patient_id, request.state.request_id
    )
    if (context.tenant_id, context.patient_id, context.prescription_id) != (
        tenant_id,
        body.patient_id,
        prescription_id,
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    if context.status != "issued":
        raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
    order = session.scalar(
        select(Order).where(Order.prescription_id == prescription_id).with_for_update()
    )
    if order is not None:
        if (order.tenant_id, order.patient_id) != (tenant_id, body.patient_id):
            raise DomainError(404, "not_found", "Resource not found.")
        if (
            order.status not in {"awaiting_payment", "cancelled"}
            or order.payment_status != "unpaid"
            or order.quote_id
            or order.payment_id
            or order.delivery_id
            or order.medicine_status != "not_ready"
        ):
            raise DomainError(
                409, "prescription_correction_locked", "Checkout, payment or preparation has begun."
            )
        order.status = "cancelled"
        order.updated_at = datetime.now(timezone.utc)
    session.add(
        PrescriptionCorrectionHold(
            prescription_id=prescription_id,
            tenant_id=tenant_id,
            patient_id=body.patient_id,
            corrected_by=identity.subject_id,
        )
    )
    session.commit()
    return {
        "tenant_id": tenant_id,
        "prescription_id": prescription_id,
        "patient_id": body.patient_id,
    }
