"""Current appointment checks, using the verified caller token."""

from uuid import UUID

import httpx
from pydantic import BaseModel
from telelink_common.access import has_tenant_role
from telelink_common.errors import DomainError


class Appointment(BaseModel):
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    doctor_id: UUID


def not_found():
    raise DomainError(404, "not_found", "Resource not found.")


def authorize(identity, appointment, row=None):
    own = "patient" in identity.global_roles and identity.subject_id == appointment.patient_id
    membership = next(
        (m for m in identity.memberships if m.tenant_id == appointment.tenant_id), None
    )
    doctor = identity.subject_id == appointment.doctor_id and has_tenant_role(
        membership, appointment.tenant_id, "doctor"
    )
    if not (own or doctor):
        not_found()
    if row is not None:
        fields = ["tenant_id", "appointment_id", "patient_id"]
        if row.doctor_id is not None:
            fields.append("doctor_id")
        if any(getattr(row, field) != getattr(appointment, field) for field in fields):
            not_found()


class AppointmentClient:
    def __init__(self, settings, *, transport=None):
        self.base = settings.scheduling_url
        self.client = httpx.Client(
            timeout=settings.records_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def appointment(self, appointment_id, token, request_id):
        if not self.base:
            raise DomainError(503, "unavailable", "Scheduling is not configured.")
        try:
            response = self.client.get(
                f"{self.base}/appointments/{appointment_id}",
                headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Scheduling is unavailable.") from None
        if response.status_code in {403, 404}:
            not_found()
        if response.status_code == 401:
            raise DomainError(401, "unauthenticated", "Invalid or expired access token.")
        if response.status_code >= 500:
            raise DomainError(503, "unavailable", "Scheduling is unavailable.")
        try:
            if response.status_code != 200:
                raise ValueError()
            row = Appointment.model_validate(response.json())
            if row.appointment_id != appointment_id:
                raise ValueError()
            return row
        except (ValueError, TypeError):
            raise DomainError(502, "upstream_error", "Invalid scheduling response.") from None
