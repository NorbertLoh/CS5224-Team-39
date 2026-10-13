from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from telelink_common.access import ClinicMembership, ClinicRole, CurrentIdentity

MembershipRole = ClinicRole
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


class MembershipRead(ClinicMembership):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at")
    def utc_timestamp(self, value: datetime):
        return (
            value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )


class IdentityRead(CurrentIdentity):
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
