"""Trusted context via scoped service JWTs, never cross-service database access."""

from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, StrictBool, ValidationError, field_validator, model_validator
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.lifecycle import utc


class Money(BaseModel):
    amount_minor: int = Field(strict=True, ge=0, le=9007199254740991)
    currency: Literal["SGD"]


class Appointment(BaseModel):
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: Literal[
        "held",
        "pending_payment",
        "confirmed",
        "in_progress",
        "completed",
        "expired",
        "cancelled",
        "no_show",
    ]
    starts_at: datetime
    ends_at: datetime
    payment_id: UUID | None
    payment_resolution: str
    consultation_price: Money

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware(cls, value):
        return utc(value)

    @model_validator(mode="after")
    def valid_context(self):
        if self.starts_at >= self.ends_at or self.patient_id == self.doctor_id:
            raise ValueError("Invalid appointment context")
        return self


class Payment(BaseModel):
    payment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    appointment_id: UUID | None
    purpose: str
    status: str
    resolution: str
    amount: Money


class Decision(BaseModel):
    allowed: StrictBool
    reason: str


class AdmissionSources:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.upstream_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def call(self, service, path, model, request_id, body=None):
        base = getattr(self.settings, service + "_url")
        secret = getattr(self.settings, service + "_secret")
        if base is None or secret is None:
            raise DomainError(503, "unavailable", "Required service is not configured.")
        audience = "telelink-" + service + "-consultation"
        try:
            response = self.client.request(
                "GET" if body is None else "POST",
                base + path,
                json=body,
                headers={
                    "Authorization": "Bearer " + service_token(secret, "consultation", audience),
                    "X-Request-ID": request_id,
                },
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Required service is unavailable.") from None
        if response.status_code in {403, 404}:
            raise DomainError(404, "not_found", "Resource not found.")
        if response.status_code == 401 or response.status_code >= 500:
            raise DomainError(503, "unavailable", "Required service is unavailable.")
        try:
            if response.status_code != 200:
                raise ValueError()
            return model.model_validate(response.json())
        except (ValueError, TypeError, ValidationError):
            raise DomainError(502, "upstream_error", "Invalid upstream response.") from None

    def appointment(self, appointment_id, request_id):
        row = self.call(
            "scheduling", f"/internal/appointments/{appointment_id}", Appointment, request_id
        )
        if row.appointment_id != appointment_id:
            raise DomainError(502, "upstream_error", "Invalid upstream appointment.")
        return row

    def validate(self, appointment, subject_id, request_id):
        if subject_id not in {appointment.patient_id, appointment.doctor_id}:
            raise DomainError(404, "not_found", "Resource not found.")
        decision = self.call(
            "identity",
            "/access-decisions",
            Decision,
            request_id,
            {
                "subject_id": str(subject_id),
                "tenant_id": str(appointment.tenant_id),
                "action": "consultation.join",
                "resource": {
                    key: str(getattr(appointment, key))
                    for key in ("appointment_id", "patient_id", "doctor_id")
                },
            },
        )
        expected_reason = (
            "own_appointment" if subject_id == appointment.patient_id else "assigned_doctor"
        )
        if not decision.allowed or decision.reason != expected_reason:
            raise DomainError(404, "not_found", "Resource not found.")
        if (
            appointment.status not in {"confirmed", "in_progress"}
            or appointment.payment_resolution != "confirmed"
            or appointment.payment_id is None
        ):
            raise DomainError(409, "admission_denied", "Appointment is not eligible for admission.")
        payment = self.call(
            "billing", f"/internal/payments/{appointment.payment_id}", Payment, request_id
        )
        if (
            payment.payment_id != appointment.payment_id
            or payment.tenant_id != appointment.tenant_id
            or payment.patient_id != appointment.patient_id
            or payment.appointment_id != appointment.appointment_id
            or payment.purpose != "consultation"
            or payment.status != "succeeded"
            or payment.resolution != "none"
            or payment.amount != appointment.consultation_price
        ):
            raise DomainError(409, "admission_denied", "Payment is not eligible for admission.")
