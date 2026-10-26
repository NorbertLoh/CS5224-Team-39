"""Durable, at-most-once submission intent and verified reference reconciliation."""

from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select
from telelink_common.errors import DomainError, ErrorEnvelope

from app.access import order_scope
from app.api.dependencies import DB, Identity
from app.models import Delivery, Order
from app.schemas import DeliveryPublic

router = APIRouter(
    tags=["deliveries"], responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 503)}
)


@router.get("/deliveries/{delivery_id}", response_model=DeliveryPublic)
def get_delivery(delivery_id: UUID, identity: Identity, session: DB):
    delivery = session.scalar(
        select(Delivery)
        .join(Order, Delivery.order_id == Order.order_id)
        .where(
            Delivery.delivery_id == delivery_id,
            order_scope(identity),
        )
    )
    if delivery is None:
        raise DomainError(404, "not_found", "Resource not found.")
    return DeliveryPublic.model_validate(delivery)
