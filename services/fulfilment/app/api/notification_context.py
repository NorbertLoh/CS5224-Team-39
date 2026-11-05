from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.api.dependencies import DB
from app.models import Delivery, Order
from app.services.pricing import saved_prices

router = APIRouter(tags=["internal"])
notification_service = require_service(
    "notification", "telelink-fulfilment-notification", "notification_secret"
)


@router.get(
    "/internal/deliveries/{resource_id}/notification-context",
    dependencies=[Depends(notification_service)],
)
def notification_context(resource_id: UUID, tenant_id: UUID, session: DB, response: Response):
    row = session.get(Delivery, resource_id)
    order = session.get(Order, row.order_id) if row is not None else None
    if row is None or order is None or order.tenant_id != tenant_id or row.tenant_id != tenant_id:
        raise DomainError(404, "not_found", "Resource not found.")
    response.headers["Cache-Control"] = "no-store"
    return {
        "resource_id": row.delivery_id,
        "tenant_id": order.tenant_id,
        "patient_id": order.patient_id,
        "order_id": order.order_id,
        "status": row.status,
        "eligible": order.delivery_id == row.delivery_id,
    }


@router.get(
    "/internal/prescriptions/{resource_id}/notification-context",
    dependencies=[Depends(notification_service)],
)
def pricing_context(
    resource_id: UUID,
    tenant_id: UUID,
    patient_id: UUID,
    request: Request,
    session: DB,
    response: Response,
):
    source = request.app.state.dispensing.get(resource_id, patient_id, request.state.request_id)
    if (source.prescription_id, source.tenant_id, source.patient_id) != (
        resource_id,
        tenant_id,
        patient_id,
    ):
        raise DomainError(404, "not_found", "Resource not found.")
    prices = saved_prices(session, tenant_id, resource_id)
    expected = {item.prescription_item_id for item in source.items}
    order = session.scalar(
        select(Order).where(Order.tenant_id == tenant_id, Order.prescription_id == resource_id)
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "resource_id": resource_id,
        "prescription_id": resource_id,
        "appointment_id": source.appointment_id,
        "tenant_id": tenant_id,
        "patient_id": source.patient_id,
        "eligible": source.status == "issued"
        and bool(expected)
        and {item.prescription_item_id for item in prices} == expected
        and (
            order is None
            or (order.status == "awaiting_payment" and order.payment_status == "unpaid")
        ),
    }
