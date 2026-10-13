from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

MembershipRole = Literal["doctor", "clinic_admin"]
MembershipStatus = Literal["active", "revoked"]
Action = Literal[
    "appointment.read", "appointment.cancel", "clinical.read", "clinical.write", "medicine.ready"
]


class MembershipWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[MembershipRole] = Field(min_length=1, max_length=2)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, roles):
        if len(set(roles)) != len(roles):
            raise ValueError("roles must be unique")
        return roles


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    membership_id: UUID
    subject_id: UUID
    tenant_id: UUID
    roles: list[MembershipRole]
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def utc_timestamp(self, value: datetime):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )


class IdentityRead(BaseModel):
    subject_id: UUID
    cognito_sub: str
    display_name: str
    global_roles: list[Literal["patient", "platform_admin"]]
    memberships: list[MembershipRead]


class MembershipPage(BaseModel):
    items: list[MembershipRead]
    next_cursor: str | None


class AppointmentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: UUID
    tenant_id: UUID
    action: Action
    resource: AppointmentContext


class AccessDecision(BaseModel):
    allowed: bool
    reason: Literal[
        "own_appointment", "assigned_doctor", "clinic_admin", "platform_admin", "not_authorized"
    ]


class ErrorDetail(BaseModel):
    field: str
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ErrorDetail]


class ErrorEnvelope(BaseModel):
    error: ErrorBody
