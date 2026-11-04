"""Live tenant validation, with an explicit local-only fixture option."""

import json
import time
from uuid import UUID

import httpx
import jwt
from telelink_common.errors import DomainError


class ClinicDirectory:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = None
        if settings.tenant_url is not None:
            self.client = httpx.Client(
                base_url=settings.tenant_url + "/",
                timeout=settings.tenant_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            )
        self.tenant_ids = None
        fixture_path = settings.clinic_fixture_path
        if fixture_path is not None:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            if data.get("fixture_kind") != "synthetic_shared_dataset":
                raise ValueError("clinic_fixture_path requires the agreed F14 dataset")
            self.tenant_ids = {UUID(clinic["tenant_id"]) for clinic in data["clinics"]}

    def close(self):
        if self.client is not None:
            self.client.close()

    def require_clinic(self, tenant_id: UUID, request_id: str):
        if self.client is not None:
            now = int(time.time())
            token = jwt.encode(
                {
                    "iss": "telelink-service:identity",
                    "aud": "telelink-tenant-memberships",
                    "sub": "identity",
                    "iat": now,
                    "exp": now + 60,
                },
                self.settings.identity_secret.get_secret_value(),
                algorithm="HS256",
            )
            try:
                response = self.client.get(
                    f"internal/clinics/{tenant_id}/membership-profile",
                    headers={"Authorization": "Bearer " + token, "X-Request-ID": request_id},
                )
                if response.status_code == 404:
                    raise DomainError(404, "not_found", "Resource not found.")
                if response.status_code != 200:
                    raise ValueError("Clinic lookup failed")
                if UUID(response.json()["tenant_id"]) != tenant_id:
                    raise ValueError("Clinic acknowledgement mismatch")
            except (httpx.RequestError, ValueError, TypeError, KeyError, AttributeError):
                raise DomainError(503, "unavailable", "Clinic validation is unavailable.") from None
            return
        if self.tenant_ids is None:
            raise DomainError(503, "unavailable", "Clinic validation is not configured.")
        if tenant_id not in self.tenant_ids:
            raise DomainError(404, "not_found", "Resource not found.")
