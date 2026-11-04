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
    node_id: UUID | None = None
    node_token: str | None = Field(
        default=None, min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$", repr=False
    )


class RenewalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    peer_id: UUID


class NodeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: UUID
    node_token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    internal_url: str = Field(max_length=100)
    draining: bool = False


class LeasePublic(BaseModel):
    session_id: UUID
    tenant_id: UUID
    appointment_id: UUID
    subject_id: UUID
    peer_id: UUID
    expires_at: datetime
    node_id: UUID | None = None
    assignment_version: int | None = None

    @field_serializer("expires_at")
    def timestamp(self, value):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )


class AdmissionPublic(LeasePublic):
    token: str = Field(repr=False)
    ice_servers: list[dict] = Field(default_factory=list)
    relay_only: bool = False
    signalling_path: str = "/peerjs"
    call_expires_at: datetime
