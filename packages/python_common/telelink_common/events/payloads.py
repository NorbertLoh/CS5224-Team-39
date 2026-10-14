"""Per-event `data` payload models for the C05 event types."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints


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


class DocumentReady(EventData):
    document_id: UUID
    prescription_id: UUID
    appointment_id: UUID


class DeliveryStatusChanged(EventData):
    delivery_id: UUID
    order_id: UUID
    status: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
