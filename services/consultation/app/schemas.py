from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AdmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: UUID


class LeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    peer_id: UUID


class LeasePublic(BaseModel):
    session_id: UUID
    tenant_id: UUID
    appointment_id: UUID
    subject_id: UUID
    peer_id: UUID
    expires_at: datetime

    @field_serializer("expires_at")
    def timestamp(self, value):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )


class AdmissionPublic(LeasePublic):
    token: str = Field(repr=False)
