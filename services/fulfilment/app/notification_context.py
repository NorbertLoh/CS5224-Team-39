from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError
from telelink_common.service_auth import require_service

from app.database import get_session
from app.models import Delivery, Order

router = APIRouter(tags=["internal"])
DB = Annotated[Session, Depends(get_session)]
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
