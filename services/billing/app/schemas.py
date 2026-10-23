from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.refund_policy import RefundAvailability, refund_availability


class Money(BaseModel):
    amount_minor: int = Field(strict=True, ge=0, le=9007199254740991)
    currency: Literal["SGD"]


class CheckoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: UUID


class MedicationCheckoutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: UUID
    quote_id: UUID


class MedicationResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: Literal["refund_required"]
    resource_id: UUID
    reason: Literal[
        "quote_expired",
        "order_cancelled",
        "delivery_price_changed",
        "duplicate_charge",
        "late_payment",
        "slot_reallocated",
        "appointment_cancelled",
        "appointment_unavailable",
    ]


class MedicationLine(BaseModel):
    prescription_item_id: UUID
    medication_id: UUID
    quantity: int = Field(strict=True, gt=0, le=9007199254740991)
    unit_price: Money
    line_total: Money

    @model_validator(mode="after")
    def total_matches(self):
        if self.quantity * self.unit_price.amount_minor != self.line_total.amount_minor:
            raise ValueError("Invalid line total")
        return self


class MedicationReservation(BaseModel):
    order_id: UUID
    quote_id: UUID
    tenant_id: UUID
    patient_id: UUID
    payment_id: UUID
    status: Literal["awaiting_payment"]
    payment_status: Literal["pending"]
    quote_status: Literal["accepted"]
    items: list[MedicationLine] = Field(min_length=1, max_length=1000)
    medication_subtotal: Money
    delivery_fee: Money
    total: Money
    expires_at: datetime

    @model_validator(mode="after")
    def validate_snapshot(self):
        ids = [line.prescription_item_id for line in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate prescription item")
        if (
            sum(line.line_total.amount_minor for line in self.items)
            != self.medication_subtotal.amount_minor
        ):
            raise ValueError("Invalid medication subtotal")
        if (
            self.medication_subtotal.amount_minor + self.delivery_fee.amount_minor
            != self.total.amount_minor
        ):
            raise ValueError("Invalid quote total")
        if self.expires_at.tzinfo is None:
            raise ValueError("Timezone required")
        return self


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
    refund_availability: RefundAvailability = "unsupported_payment"
    created_at: datetime
    updated_at: datetime


class CheckoutPublic(BaseModel):
    payment: PaymentPublic
    checkout_url: str
    expires_at: datetime


class PaymentPage(BaseModel):
    items: list[PaymentPublic]
    next_cursor: str | None


class CommissionTotals(BaseModel):
    payment_count: int
    amount: Money
    commission_amount: Money
    clinic_amount: Money


def payment_public(payment):
    return PaymentPublic(
        **{
            field: getattr(payment, field)
            for field in PaymentPublic.model_fields
            if field not in {"amount", "commission_amount", "clinic_amount", "refund_availability"}
        },
        **{
            field: Money(amount_minor=getattr(payment, column), currency=payment.currency)
            for field, column in (
                ("amount", "amount_minor"),
                ("commission_amount", "commission_amount_minor"),
                ("clinic_amount", "clinic_amount_minor"),
            )
        },
        refund_availability=refund_availability(payment),
    )
