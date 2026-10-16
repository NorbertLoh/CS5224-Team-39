"""Validated render snapshots supplied by trusted records/billing adapters later."""

from datetime import date

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StrictInt,
    model_validator,
)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Header(Snapshot):
    clinic_name: str = Field(min_length=1, max_length=200)
    clinic_address: str = Field(min_length=1, max_length=500)
    patient_name: str = Field(min_length=1, max_length=200)
    reference: str = Field(min_length=1, max_length=100)
    issued_at: AwareDatetime


class PrescriptionItem(Snapshot):
    display_name: str = Field(min_length=1, max_length=200)
    quantity: PositiveInt
    instructions: str = Field(min_length=1, max_length=20000)


class Prescription(Header):
    clinic_address: str | None = Field(default=None, min_length=1, max_length=500)
    doctor_name: str = Field(min_length=1, max_length=200)
    doctor_registration: str | None = Field(default=None, min_length=1, max_length=100)
    items: tuple[PrescriptionItem, ...] = Field(min_length=1, max_length=100)


class ReceiptItem(Snapshot):
    description: str = Field(min_length=1, max_length=200)
    amount_minor: StrictInt = Field(ge=0, le=9007199254740991)


class Receipt(Header):
    payment_reference: str = Field(min_length=1, max_length=200)
    paid_at: AwareDatetime
    currency: str = Field(default="SGD", pattern="^SGD$")
    items: tuple[ReceiptItem, ...] = Field(min_length=1, max_length=100)
    total_minor: StrictInt = Field(ge=0, le=9007199254740991)

    @model_validator(mode="after")
    def check_total(self):
        if sum(item.amount_minor for item in self.items) != self.total_minor:
            raise ValueError("Receipt lines must equal the trusted paid total")
        if self.paid_at > self.issued_at:
            raise ValueError("Receipt cannot be issued before payment")
        return self


class MedicalCertificate(Header):
    doctor_name: str = Field(min_length=1, max_length=200)
    doctor_registration: str = Field(min_length=1, max_length=100)
    consultation_date: date
    unfit_from: date
    unfit_through: date

    @model_validator(mode="after")
    def check_period(self):
        if self.unfit_through < self.unfit_from:
            raise ValueError("MC end date must be on or after its start date")
        return self
