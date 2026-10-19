"""Minimum C04 projection boundary. No clinical database access or patient prices."""

import json
from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import Field, model_validator
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.schemas import StrictModel


class DispensingItem(StrictModel):
    prescription_item_id: UUID
    medication_id: UUID
    quantity: int = Field(strict=True, gt=0, le=9007199254740991)


class DispensingContext(StrictModel):
    prescription_id: UUID
    appointment_id: UUID
    tenant_id: UUID
    patient_id: UUID
    status: Literal["draft", "issued", "voided"]
    items: list[DispensingItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [item.prescription_item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate prescription item IDs")
        return self


class DispensingSource(Protocol):
    def get(
        self, prescription_id: UUID, patient_id: UUID, request_id: str
    ) -> DispensingContext: ...


class UnavailableDispensing:
    def get(self, prescription_id, patient_id, request_id):
        raise DomainError(503, "unavailable", "Dispensing context is not configured.")


class HttpDispensing:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=3, trust_env=False, follow_redirects=False, transport=transport
        )

    def close(self):
        self.client.close()

    def get(self, prescription_id, patient_id, request_id):
        config = self.settings
        if not config.records_url or not config.records_secret:
            raise DomainError(503, "unavailable", "Dispensing source is not configured.")
        try:
            response = self.client.get(
                f"{config.records_url}/internal/prescriptions/{prescription_id}/dispensing",
                params={"patient_id": str(patient_id), "purpose": "dispensing"},
                headers={
                    "Authorization": "Bearer "
                    + service_token(
                        config.records_secret, "fulfilment", "telelink-records-fulfilment"
                    ),
                    "X-Request-ID": request_id,
                },
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Dispensing source is unavailable.") from None
        if response.status_code == 404:
            raise DomainError(404, "not_found", "Resource not found.")
        if response.status_code == 409:
            raise DomainError(409, "prescription_not_issued", "Prescription must be issued.")
        if response.status_code != 200:
            raise DomainError(503, "unavailable", "Dispensing source is unavailable.")
        try:
            result = DispensingContext.model_validate(response.json())
            if (result.prescription_id, result.patient_id) != (prescription_id, patient_id):
                raise ValueError("Context mismatch")
            return result
        except (ValueError, TypeError):
            raise DomainError(502, "upstream_error", "Invalid dispensing response.") from None


class FixtureDispensing:
    """Opt-in synthetic fixture only; Settings disallows this outside local/test."""

    def __init__(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Project the agreed C04 example, intentionally dropping instructions and doctor content.
        raw = data["prescription"]
        self.context = DispensingContext.model_validate(
            {
                key: raw[key]
                for key in (
                    "prescription_id",
                    "appointment_id",
                    "tenant_id",
                    "patient_id",
                    "status",
                )
            }
            | {
                "items": [
                    {
                        key: item[key]
                        for key in ("prescription_item_id", "medication_id", "quantity")
                    }
                    for item in raw["items"]
                ]
            }
        )

    def get(self, prescription_id, patient_id, request_id):
        if (self.context.prescription_id, self.context.patient_id) != (prescription_id, patient_id):
            raise DomainError(404, "not_found", "Resource not found.")
        return self.context.model_copy(deep=True)
