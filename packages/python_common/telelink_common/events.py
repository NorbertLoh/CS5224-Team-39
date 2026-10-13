"""C05 workflow event envelope, routing registry and transport validation.

Pure validation only: publication/retry tracking is M02 and SQS acknowledgement and
inbox deduplication are M03. Errors never echo payload values.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

CONSUMERS = frozenset({"scheduling", "fulfilment", "document", "notification"})
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


class EventValidationError(ValueError):
    """A malformed, unsupported or misrouted event; never acknowledge it as success."""


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


@dataclass(frozen=True)
class EventType:
    detail_type: str
    source: str
    data_model: type[EventData]
    consumers: frozenset[str]


EVENT_TYPES = {
    spec.detail_type: spec
    for spec in (
        EventType(
            "consultation_payment_succeeded.v1",
            "telelink.billing",
            ConsultationPaymentSucceeded,
            frozenset({"scheduling"}),
        ),
        EventType(
            "medication_payment_succeeded.v1",
            "telelink.billing",
            MedicationPaymentSucceeded,
            frozenset({"fulfilment"}),
        ),
        EventType(
            "appointment_confirmed.v1",
            "telelink.scheduling",
            AppointmentConfirmed,
            frozenset({"notification"}),
        ),
        EventType(
            "prescription_issued.v1",
            "telelink.clinical-records",
            PrescriptionIssued,
            frozenset({"document"}),
        ),
        EventType(
            "document_ready.v1",
            "telelink.document",
            DocumentReady,
            frozenset({"notification"}),
        ),
        EventType(
            "delivery_status_changed.v1",
            "telelink.fulfilment",
            DeliveryStatusChanged,
            frozenset({"notification"}),
        ),
    )
}


def format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


class WorkflowEvent(BaseModel):
    """One C05 event: its DetailType plus the `Detail` envelope fields."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    detail_type: str
    event_id: UUID
    schema_version: StrictInt = 1
    occurred_at: datetime
    tenant_id: UUID
    correlation_id: UUID
    data: SerializeAsAny[EventData]

    @model_validator(mode="before")
    @classmethod
    def validate_data_for_type(cls, values):
        if not isinstance(values, Mapping):
            return values
        spec = EVENT_TYPES.get(values.get("detail_type"))
        if spec is None:
            raise ValueError("unsupported event type")
        data = values.get("data")
        if isinstance(data, EventData) and not isinstance(data, spec.data_model):
            raise ValueError("data does not match the event type")
        if not isinstance(data, EventData):
            data = spec.data_model.model_validate(data)
        return {**values, "data": data}

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported schema_version")
        return value

    @field_validator("occurred_at", mode="before")
    @classmethod
    def validate_occurred_at(cls, value):
        if isinstance(value, str) and not _TIMESTAMP.fullmatch(value):
            raise ValueError("occurred_at must be UTC RFC 3339 with milliseconds and Z")
        return value

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at requires a timezone")
        value = value.astimezone(timezone.utc)
        return value.replace(microsecond=value.microsecond // 1000 * 1000)

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return format_timestamp(value)

    @property
    def source(self) -> str:
        return EVENT_TYPES[self.detail_type].source

    def detail(self) -> dict:
        return self.model_dump(mode="json", exclude={"detail_type"})


def _safe_error(prefix: str, error: ValidationError) -> EventValidationError:
    problems = ", ".join(
        ".".join(str(part) for part in item["loc"]) + f" ({item['type']})"
        for item in error.errors()
    )
    return EventValidationError(f"{prefix}: {problems}")


def new_event(
    detail_type: str,
    *,
    tenant_id: UUID | str,
    correlation_id: UUID | str,
    occurred_at: datetime,
    data: EventData | Mapping,
    event_id: UUID | str | None = None,
) -> WorkflowEvent:
    """Create an event for a committed fact; keep the returned event_id for retries."""
    try:
        return WorkflowEvent(
            detail_type=detail_type,
            event_id=event_id or uuid4(),
            occurred_at=occurred_at,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            data=data,
        )
    except ValidationError as error:
        raise _safe_error("invalid event", error) from None


def to_put_events_entry(event: WorkflowEvent, event_bus_name: str) -> dict:
    """Build one EventBridge PutEvents entry; Detail is serialized exactly once."""
    detail = event.detail()
    return {
        "EventBusName": event_bus_name,
        "Source": event.source,
        "DetailType": event.detail_type,
        "Time": detail["occurred_at"],
        "Detail": json.dumps(detail, separators=(",", ":")),
    }


def _parse(source, detail_type, detail, consumer: str | None) -> WorkflowEvent:
    spec = EVENT_TYPES.get(detail_type) if isinstance(detail_type, str) else None
    if spec is None:
        raise EventValidationError("unsupported event type")
    if source != spec.source:
        raise EventValidationError("event source does not match its type")
    if consumer is not None:
        if consumer not in CONSUMERS:
            raise ValueError("unknown consumer")
        if consumer not in spec.consumers:
            raise EventValidationError("event type is not routed to this consumer")
    if not isinstance(detail, Mapping):
        raise EventValidationError("event detail must be a JSON object")
    try:
        return WorkflowEvent.model_validate({**detail, "detail_type": detail_type})
    except ValidationError as error:
        raise _safe_error("invalid event detail", error) from None


def parse_put_events_entry(entry: Mapping) -> WorkflowEvent:
    """Validate a producer PutEvents entry, such as the C05 fixtures."""
    try:
        detail = json.loads(entry["Detail"])
    except (KeyError, TypeError, ValueError):
        raise EventValidationError("Detail must be a JSON string") from None
    event = _parse(entry.get("Source"), entry.get("DetailType"), detail, None)
    if entry.get("Time") != format_timestamp(event.occurred_at):
        raise EventValidationError("Time must equal occurred_at")
    return event


def parse_sqs_body(body: str | bytes, *, consumer: str) -> WorkflowEvent:
    """Parse an SQS message body holding the full EventBridge event, once."""
    try:
        wrapper = json.loads(body)
    except (TypeError, ValueError):
        raise EventValidationError("message body must be JSON") from None
    if not isinstance(wrapper, Mapping):
        raise EventValidationError("message body must be an EventBridge event object")
    return _parse(
        wrapper.get("source"), wrapper.get("detail-type"), wrapper.get("detail"), consumer
    )
