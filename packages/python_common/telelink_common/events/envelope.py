"""The C05 `Detail` envelope model and producer-side event construction."""

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializeAsAny,
    StrictInt,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from telelink_common.events.errors import safe_error
from telelink_common.events.payloads import EventData
from telelink_common.events.registry import EVENT_TYPES

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")


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
        raise safe_error("invalid event", error) from None
