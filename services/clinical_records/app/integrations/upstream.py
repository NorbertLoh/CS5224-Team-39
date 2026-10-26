"""Call owning services with the verified user's token; never read their databases."""

from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, StrictBool, ValidationError
from telelink_common.errors import DomainError


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


class Medication(BaseModel):
    medication_id: UUID
    tenant_id: UUID
    display_name: str
    active: StrictBool


class CataloguePage(BaseModel):
    items: list[Medication]
    next_cursor: str | None


class CorrectionHold(BaseModel):
    tenant_id: UUID
    prescription_id: UUID
    patient_id: UUID


def not_found():
    raise DomainError(404, "not_found", "Resource not found.")


class RecordsUpstream:
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

    def get(self, base, path, token, request_id, model, params=None):
        if base is None:
            raise DomainError(503, "unavailable", "Required upstream is not configured.")
        try:
            response = self.client.get(
                base + path,
                params=params,
                headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
            )
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Required upstream is unavailable.") from None
        if response.status_code in {403, 404}:
            not_found()
        if response.status_code == 401:
            raise DomainError(401, "unauthenticated", "Invalid or expired access token.")
        if response.status_code >= 500:
            raise DomainError(503, "unavailable", "Required upstream is unavailable.")
        try:
            if response.status_code != 200:
                raise ValueError()
            return model.model_validate(response.json())
        except (ValueError, TypeError, ValidationError):
            raise DomainError(502, "upstream_error", "Invalid upstream response.") from None

    def appointment(self, appointment_id, token, request_id):
        row = self.get(
            self.settings.scheduling_url,
            f"/appointments/{appointment_id}",
            token,
            request_id,
            Appointment,
        )
        if row.appointment_id != appointment_id:
            raise DomainError(502, "upstream_error", "Invalid upstream response.")
        return row

    def prepare_correction(self, tenant_id, prescription_id, patient_id, token, request_id):
        base = self.settings.fulfilment_url
        if base is None:
            raise DomainError(503, "unavailable", "Fulfilment is not configured.")
        try:
            response = self.client.post(
                f"{base}/clinics/{tenant_id}/prescriptions/{prescription_id}/prepare-correction",
                json={"patient_id": str(patient_id)},
                headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
            )
        except httpx.RequestError:
            raise DomainError(
                503, "unavailable", "Fulfilment is unavailable; retry the correction."
            ) from None
        if response.status_code in {403, 404}:
            not_found()
        if response.status_code == 409:
            raise DomainError(
                409, "prescription_correction_locked", "Checkout, payment or preparation has begun."
            )
        try:
            if response.status_code != 200:
                raise ValueError()
            hold = CorrectionHold.model_validate(response.json())
            if (hold.tenant_id, hold.prescription_id, hold.patient_id) != (
                tenant_id,
                prescription_id,
                patient_id,
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise DomainError(
                503, "unavailable", "Could not reserve the prescription correction; retry."
            ) from None

    def medications(self, tenant_id, ids, token, request_id):
        found, seen, cursor = {}, set(), None
        # Bound a malformed/cycling provider without accepting a partial catalogue.
        for _ in range(100):
            page = self.get(
                self.settings.fulfilment_url,
                f"/clinics/{tenant_id}/catalogue",
                token,
                request_id,
                CataloguePage,
                {"limit": 100, **({"cursor": cursor} if cursor else {})},
            )
            for item in page.items:
                if item.tenant_id != tenant_id or not item.display_name.strip():
                    raise DomainError(502, "upstream_error", "Invalid upstream response.")
                if item.active and item.medication_id in ids:
                    found[item.medication_id] = item.display_name
            if ids <= found.keys():
                return found
            cursor = page.next_cursor
            if cursor is None:
                raise DomainError(409, "medication_unavailable", "Medication is unavailable.")
            if cursor in seen:
                break
            seen.add(cursor)
        raise DomainError(502, "upstream_error", "Invalid upstream pagination.")
