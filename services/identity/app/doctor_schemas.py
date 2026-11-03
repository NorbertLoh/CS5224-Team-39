from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApplicationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    legal_name: str = Field(min_length=1, max_length=200)
    licence_number: str = Field(min_length=1, max_length=100)
    licensing_authority: str = Field(min_length=1, max_length=200)
    specialty: str = Field(min_length=1, max_length=200)
    document_id: UUID
    expected_revision: int = Field(ge=0)


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subject_id: UUID
    legal_name: str
    licence_number: str
    licensing_authority: str
    specialty: str
    document_id: UUID
    status: Literal["pending", "approved", "rejected", "revoked"]
    revision: int
    rejection_reason: str | None
    submitted_at: datetime
    reviewed_at: datetime | None


class ReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["approved", "rejected", "revoked"]
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=1)


class ApplicationCounts(BaseModel):
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    revoked: int = 0
    total: int = 0


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: UUID
    actor_id: UUID
    action: str
    snapshot: dict
    created_at: datetime
