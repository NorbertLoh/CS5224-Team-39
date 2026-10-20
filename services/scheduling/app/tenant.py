"""Live tenant gate and doctor directory; no clinic or membership fixtures."""

import time
from typing import Literal
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, Field
from telelink_common.errors import DomainError

from app.schemas import Money


class BookingProfile(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=1)
    status: Literal["active"]
    consultation_price: Money


class DoctorSummary(BaseModel):
    doctor_id: UUID
    display_name: str = Field(min_length=1)


class DoctorPage(BaseModel):
    items: list[DoctorSummary]
    next_cursor: str | None = Field(max_length=4096)


class TenantClient:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = (
            httpx.Client(
                base_url=settings.tenant_url + "/",
                timeout=settings.identity_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            )
            if settings.tenant_url
            else None
        )

    def close(self):
        if self.client is not None:
            self.client.close()

    def get(self, path, request_id, *, params=None, authenticated=False):
        if self.client is None:
            raise DomainError(503, "unavailable", "Tenant service is not configured.")
        headers = {"X-Request-ID": request_id}
        if authenticated:
            if self.settings.scheduling_secret is None:
                raise DomainError(503, "unavailable", "Tenant credential is not configured.")
            now = int(time.time())
            headers["Authorization"] = "Bearer " + jwt.encode(
                {
                    "iss": "telelink-service:scheduling",
                    "aud": "telelink-tenant-booking",
                    "sub": "scheduling",
                    "iat": now,
                    "exp": now + 60,
                },
                self.settings.scheduling_secret.get_secret_value(),
                algorithm="HS256",
            )
        try:
            response = self.client.get(path, params=params, headers=headers)
        except httpx.RequestError:
            raise DomainError(503, "unavailable", "Tenant service is unavailable.") from None
        if response.status_code == 404:
            raise DomainError(404, "not_found", "Resource not found.")
        if authenticated and response.status_code == 409:
            raise DomainError(409, "clinic_not_active", "Clinic cannot accept new bookings.")
        if response.status_code != 200:
            raise DomainError(503, "unavailable", "Tenant service is unavailable.")
        return response

    def booking_profile(self, tenant_id, request_id, *, public=False):
        try:
            response = self.get(
                f"internal/clinics/{tenant_id}/booking-profile", request_id, authenticated=True
            )
        except DomainError as error:
            if public and error.status_code == 409:
                raise DomainError(404, "not_found", "Resource not found.") from None
            raise
        try:
            profile = BookingProfile.model_validate(response.json())
            if profile.tenant_id != tenant_id:
                raise ValueError("Mismatched clinic")
            return profile
        except (ValueError, TypeError):
            raise DomainError(502, "upstream_error", "Invalid clinic response.") from None

    def active_doctors(self, tenant_id, request_id):
        """Return active doctors as {doctor_id: display_name}."""
        doctors, seen = {}, set()
        cursor = None
        while True:
            params = {"limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            response = self.get(f"clinics/{tenant_id}/doctors", request_id, params=params)
            try:
                page = DoctorPage.model_validate(response.json())
                ids = [doctor.doctor_id for doctor in page.items]
                if len(ids) > 100 or len(ids) != len(set(ids)) or doctors.keys() & set(ids):
                    raise ValueError("Invalid doctor page")
                doctors.update((doctor.doctor_id, doctor.display_name) for doctor in page.items)
                cursor = page.next_cursor
                if cursor is None:
                    return doctors
                if cursor in seen or not ids:
                    raise ValueError("Non-progressing directory")
                seen.add(cursor)
            except (ValueError, TypeError):
                raise DomainError(502, "upstream_error", "Invalid doctor directory.") from None
