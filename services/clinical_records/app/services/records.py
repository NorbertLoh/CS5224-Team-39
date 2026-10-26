from sqlalchemy import delete, select, text

from app.models import PrescriptionItem, ReadAudit
from app.schemas import (
    ItemPublic,
    PrescriptionPublic,
)


def lock_appointment(session, appointment_id):
    # Serialize first inserts too: a row lock cannot lock a nonexistent note.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "clinical-records:" + str(appointment_id)},
    )


def fields(appointment):
    return appointment.model_dump(exclude={"status"})


def audit(session, actor_id, request_id, kind, record=None, appointment_id=None):
    session.add(
        ReadAudit(
            actor_id=actor_id,
            resource_type=kind,
            resource_id=(
                getattr(record, "note_id", None)
                or getattr(record, "prescription_id", None)
                or getattr(record, "medical_certificate_id", None)
            ),
            tenant_id=getattr(record, "tenant_id", None),
            appointment_id=getattr(record, "appointment_id", appointment_id),
            request_id=request_id,
        )
    )


def prescription_public(session, row):
    items = session.scalars(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id == row.prescription_id)
        .order_by(PrescriptionItem.prescription_item_id)
    ).all()
    return PrescriptionPublic(
        **{name: getattr(row, name) for name in PrescriptionPublic.model_fields if name != "items"},
        items=[ItemPublic.model_validate(item) for item in items],
    )


def replace_items(session, upstream, access_token, request_id, row, body):
    names = upstream.medications(
        row.tenant_id,
        {item.medication_id for item in body.items},
        access_token,
        request_id,
    )
    session.execute(
        delete(PrescriptionItem).where(PrescriptionItem.prescription_id == row.prescription_id)
    )
    session.add_all(
        [
            PrescriptionItem(
                **item.model_dump(),
                prescription_id=row.prescription_id,
                tenant_id=row.tenant_id,
                display_name=names[item.medication_id],
            )
            for item in body.items
        ]
    )
    session.flush()
