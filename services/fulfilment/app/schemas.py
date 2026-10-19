from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

MAX_MONEY = 9007199254740991
OrderStatus = Literal[
    "awaiting_payment", "paid", "submitting", "dispatched", "delivered", "cancelled", "exception"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Money(StrictModel):
    amount_minor: int = Field(strict=True, ge=0, le=MAX_MONEY)
    currency: Literal["SGD"]


class CatalogueWrite(StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    unit_label: str = Field(min_length=1, max_length=80)
    unit_price: Money
    active: bool = Field(strict=True)


class Resource(StrictModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_field(self, value):
        if isinstance(value, datetime):
            return (
                value.astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
        return value


class CataloguePublic(Resource, CatalogueWrite):
    medication_id: UUID
    tenant_id: UUID
    updated_at: datetime


class CataloguePage(BaseModel):
    items: list[CataloguePublic]
    next_cursor: str | None


class OrderCreate(StrictModel):
    prescription_id: UUID


class MedicineReady(StrictModel):
    """The action accepts no client-controlled state or resource links."""


class DeliveryPublic(Resource):
    model_config = ConfigDict(from_attributes=True)
    delivery_id: UUID
    order_id: UUID
    tenant_id: UUID
    status: Literal[
        "pending", "submitted", "picked_up", "delivered", "cancelled", "failed", "unknown"
    ]
    created_at: datetime
    updated_at: datetime


class OrderItemPublic(StrictModel):
    prescription_item_id: UUID
    medication_id: UUID
    display_name: str
    quantity: int
    unit_price: Money
    line_total: Money


class OrderOperational(Resource):
    order_id: UUID
    tenant_id: UUID
    prescription_id: UUID
    appointment_id: UUID
    patient_id: UUID
    status: OrderStatus
    medicine_status: Literal["not_ready", "ready"]
    payment_status: Literal["unpaid", "pending", "succeeded", "refund_required", "refunded"]
    payment_id: UUID | None
    quote_id: UUID | None
    delivery_id: UUID | None
    medication_subtotal: Money
    delivery_fee: Money | None
    total: Money | None
    created_at: datetime
    updated_at: datetime


class OrderPublic(OrderOperational):
    items: list[OrderItemPublic]


class OrderPage(BaseModel):
    items: list[OrderPublic | OrderOperational]
    next_cursor: str | None


class Destination(StrictModel):
    address_line: str = Field(min_length=1, max_length=300, pattern=r"^[^\x00-\x1f\x7f]+$")
    postal_code: str = Field(pattern=r"^[0-9]{6}$")
    country_code: Literal["SG"]


class QuoteCreate(StrictModel):
    destination: Destination


class QuotePublic(Resource):
    quote_id: UUID
    order_id: UUID
    tenant_id: UUID
    status: Literal["active", "accepted", "expired", "superseded"]
    medication_subtotal: Money
    delivery_fee: Money
    total: Money
    expires_at: datetime
    created_at: datetime
