from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def utc_instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp requires a timezone")
    return value.astimezone(timezone.utc)


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(strict=True, ge=0, le=9007199254740991)
    currency: Literal["SGD"]


class SlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def textual_instant(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Timestamp requires an ISO 8601 string")
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timezone_required(cls, value):
        return utc_instant(value)

    @model_validator(mode="after")
    def fixed_duration(self):
        if self.ends_at - self.starts_at != timedelta(minutes=30):
            raise ValueError("Slots must last exactly 30 minutes")
        return self


class SlotPublic(SlotCreate):
    slot_id: UUID
    tenant_id: UUID
    doctor_id: UUID
    availability: Literal["available", "unavailable"]
    consultation_price: Money

    @field_serializer("starts_at", "ends_at")
    def timestamp(self, value):
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SlotPage(BaseModel):
    items: list[SlotPublic]
    next_cursor: str | None
