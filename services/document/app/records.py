"""Fetch only a context-matched issued prescription with a service credential."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, Field
from telelink_common.service_auth import service_token

from app.template_data import Prescription, PrescriptionItem


class IssuedItem(PrescriptionItem):
    prescription_item_id: UUID
    medication_id: UUID


class IssuedPrescription(BaseModel):
    prescription_id: UUID
    tenant_id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: Literal["issued"]
    issued_at: AwareDatetime
    patient_name: str = Field(min_length=1, max_length=200)
    doctor_name: str = Field(min_length=1, max_length=200)
    clinic_name: str = Field(min_length=1, max_length=200)
    items: list[IssuedItem] = Field(min_length=1, max_length=100)

    def render_data(self):
        return Prescription(
            reference=str(self.prescription_id),
            issued_at=self.issued_at,
            clinic_name=self.clinic_name,
            patient_name=self.patient_name,
            doctor_name=self.doctor_name,
            items=tuple(
                PrescriptionItem(
                    display_name=item.display_name,
                    quantity=item.quantity,
                    instructions=item.instructions,
                )
                for item in self.items
            ),
        )


class RecordsClient:
    def __init__(self, settings, *, transport=None):
        if not settings.records_url or not settings.records_secret:
            raise ValueError("records_url and records_secret are required")
        self.settings = settings
        self.client = httpx.Client(
            timeout=settings.records_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self):
        self.client.close()

    def prescription(self, event):
        try:
            response = self.client.get(
                self.settings.records_url
                + f"/internal/prescriptions/{event.data.prescription_id}/document",
                params={
                    "tenant_id": str(event.tenant_id),
                    "appointment_id": str(event.data.appointment_id),
                    "purpose": "prescription_pdf",
                },
                headers={
                    "Authorization": "Bearer "
                    + service_token(
                        self.settings.records_secret, "document", "telelink-records-document"
                    ),
                    "X-Request-ID": str(event.correlation_id),
                },
            )
            if response.status_code != 200:
                raise ValueError()
            result = IssuedPrescription.model_validate(response.json())
            if (
                result.prescription_id != event.data.prescription_id
                or result.appointment_id != event.data.appointment_id
                or result.tenant_id != event.tenant_id
            ):
                raise ValueError()
            return result
        except (httpx.RequestError, ValueError, TypeError):
            raise RuntimeError("Issued prescription lookup failed") from None
