from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Money(BaseModel):
    amount_minor: int = Field(strict=True, ge=0, le=9007199254740991)
    currency: Literal["SGD"]


class CheckoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: UUID


class Reservation(BaseModel):
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    payment_id: UUID
    status: Literal["pending_payment"]
    consultation_price: Money
    hold_expires_at: datetime

    @field_validator("hold_expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class BillingProfile(BaseModel):
    tenant_id: UUID
    status: Literal["active"]
    commission_bps: int = Field(strict=True, ge=0, le=10000)


class PaymentPublic(BaseModel):
    payment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    purpose: str
    appointment_id: UUID | None
    order_id: UUID | None
    quote_id: UUID | None
    status: str
    amount: Money
    commission_bps: int
    commission_amount: Money
    clinic_amount: Money
    resolution: str
    created_at: datetime
    updated_at: datetime


class CheckoutPublic(BaseModel):
    payment: PaymentPublic
    checkout_url: str
    expires_at: datetime


def payment_public(payment):
    return PaymentPublic(
        **{
            field: getattr(payment, field)
            for field in PaymentPublic.model_fields
            if field not in {"amount", "commission_amount", "clinic_amount"}
        },
        **{
            field: Money(amount_minor=getattr(payment, column), currency=payment.currency)
            for field, column in (
                ("amount", "amount_minor"),
                ("commission_amount", "commission_amount_minor"),
                ("clinic_amount", "clinic_amount_minor"),
            )
        },
    )
