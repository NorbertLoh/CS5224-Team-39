from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

PlainText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoteInput(Input):
    text: PlainText


class ItemInput(Input):
    medication_id: UUID
    quantity: Annotated[int, Field(strict=True, gt=0, le=10000)]
    instructions: PlainText


class PrescriptionInput(Input):
    items: Annotated[list[ItemInput], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_medications(self):
        if len({item.medication_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate medication")
        return self


class RecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", "issued_at", check_fields=False)
    def instant(self, value):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if value
            else None
        )


class NotePublic(RecordPublic):
    note_id: UUID
    text: str


class ItemPublic(ItemInput):
    model_config = ConfigDict(from_attributes=True)
    prescription_item_id: UUID
    display_name: str


class PrescriptionPublic(RecordPublic):
    prescription_id: UUID
    status: Literal["draft", "issued", "voided"]
    issued_at: datetime | None
    items: list[ItemPublic]


class PrescriptionPage(BaseModel):
    items: list[PrescriptionPublic]
    next_cursor: str | None
