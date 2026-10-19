"""Per-event `data` payload models for the C05 event types."""

from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_serializer,
    model_validator,
)


class Money(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    amount_minor: StrictInt = Field(ge=0)
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class EventData(BaseModel):
    # Consumers ignore unknown optional fields; additive changes keep .v1.
    model_config = ConfigDict(frozen=True, extra="ignore")


class ConsultationPaymentSucceeded(EventData):
    payment_id: UUID
    appointment_id: UUID
    amount: Money


class MedicationPaymentSucceeded(EventData):
    payment_id: UUID
    order_id: UUID
    amount: Money


class AppointmentConfirmed(EventData):
    appointment_id: UUID


class PrescriptionIssued(EventData):
    prescription_id: UUID
    appointment_id: UUID


class MedicalCertificateIssued(EventData):
    medical_certificate_id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID


class DocumentReady(EventData):
    document_id: UUID
    prescription_id: UUID | None = None
    medical_certificate_id: UUID | None = None
    appointment_id: UUID

    @model_serializer(mode="wrap")
    def source_fields(self, handler):
        # Preserve the existing prescription event shape (no new null fields).
        return {key: value for key, value in handler(self).items() if value is not None}

    @model_validator(mode="after")
    def one_source(self):
        if (self.prescription_id is None) == (self.medical_certificate_id is None):
            raise ValueError("Document-ready requires exactly one source")
        return self


class DeliveryStatusChanged(EventData):
    delivery_id: UUID
    order_id: UUID
    status: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
