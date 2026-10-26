from sqlalchemy import select

from app.models import PrescriptionPrice


def saved_prices(session, tenant_id, prescription_id):
    return list(
        session.scalars(
            select(PrescriptionPrice)
            .where(
                PrescriptionPrice.tenant_id == tenant_id,
                PrescriptionPrice.prescription_id == prescription_id,
            )
            .order_by(PrescriptionPrice.prescription_item_id)
        )
    )
