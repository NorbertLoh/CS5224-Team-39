"""Minimal recipient contact lookup; patient addresses stay in identity."""

from uuid import UUID

import httpx
from telelink_common.service_auth import service_token


class PatientContactUnavailable(Exception):
    pass


class HttpPatientProfiles:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=3, trust_env=False, follow_redirects=False, transport=transport
        )

    def close(self):
        self.client.close()

    def get_contact(self, patient_id):
        config = self.settings
        if not config.identity_url or not config.profile_secret:
            raise PatientContactUnavailable("Patient delivery contact is unavailable")
        try:
            response = self.client.get(
                f"{config.identity_url}/internal/patients/{patient_id}/delivery-contact",
                headers={
                    "Authorization": "Bearer "
                    + service_token(
                        config.profile_secret, "fulfilment", "telelink-identity-delivery"
                    )
                },
            )
            if response.status_code != 200:
                raise ValueError("Recipient unavailable")
            data = response.json()
            if UUID(data["patient_id"]) != patient_id:
                raise ValueError("Recipient mismatch")
            return {"name": data["name"], "phone": data["phone"]}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise PatientContactUnavailable("Patient delivery contact is unavailable") from None
