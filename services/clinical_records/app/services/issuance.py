"""Freeze a locked draft and stage its metadata-only event in the caller's transaction."""

from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from sqlalchemy import func, select
from telelink_common.errors import DomainError
from telelink_common.events import new_event
from telelink_common.outbox import add_event

from app.models import PrescriptionItem, event_outbox
from app.schemas import ItemInput, PrescriptionInput


def issuance_event_id(prescription_id):
    # Stable across request retries; the shared outbox stores the committed envelope.
    return uuid5(NAMESPACE_URL, "telelink:prescription_issued.v1:" + str(prescription_id))


def issue_draft(session, row, upstream, token, request_id):
    # Caller must hold the prescription row lock and recheck doctor/appointment access.
    if row.status == "issued":
        return
    if row.status != "draft":
        raise DomainError(409, "prescription_immutable", "Only draft prescriptions can be issued.")
    items = session.scalars(
        select(PrescriptionItem).where(PrescriptionItem.prescription_id == row.prescription_id)
    ).all()
    try:
        PrescriptionInput(
            items=[ItemInput.model_validate(item, from_attributes=True) for item in items]
        )
    except ValidationError:
        raise DomainError(409, "invalid_prescription", "Prescription items are invalid.") from None
    upstream.medications(row.tenant_id, {item.medication_id for item in items}, token, request_id)
    now = session.scalar(select(func.clock_timestamp()))
    event = new_event(
        "prescription_issued.v1",
        event_id=issuance_event_id(row.prescription_id),
        tenant_id=row.tenant_id,
        correlation_id=row.appointment_id,
        occurred_at=now,
        data={"prescription_id": row.prescription_id, "appointment_id": row.appointment_id},
    )
    row.status = "issued"
    row.issued_at = now
    session.flush()
    add_event(session, event_outbox, event)
