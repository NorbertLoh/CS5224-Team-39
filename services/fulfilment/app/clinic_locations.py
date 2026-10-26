"""Read the current pickup location without accessing tenant storage."""

from uuid import UUID

import httpx
from telelink_common.errors import DomainError
from telelink_common.service_auth import service_token

from app.delivery_provider import Stop


class HttpClinicLocations:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.Client(
            timeout=3, follow_redirects=False, trust_env=False, transport=transport
        )

    def close(self):
        self.client.close()

    def get(self, tenant_id):
        config = self.settings
        if not config.tenant_url or not config.tenant_secret:
            raise DomainError(
                503, "clinic_location_unavailable", "Clinic pickup location is unavailable."
            )
        try:
            response = self.client.get(
                f"{config.tenant_url}/internal/clinics/{tenant_id}/delivery-location",
                headers={
                    "Authorization": "Bearer "
                    + service_token(config.tenant_secret, "fulfilment", "telelink-tenant-delivery")
                },
            )
            if response.status_code != 200:
                raise ValueError("Location unavailable")
            data = response.json()
            if UUID(data["tenant_id"]) != tenant_id:
                raise ValueError("Location mismatch")
            location = data["location"]
            if location is None:
                raise DomainError(
                    409, "clinic_location_missing", "Clinic pickup location has not been saved."
                )
            return Stop.model_validate(
                {
                    "address": f"{location['address_line']}, Singapore {location['postal_code']}",
                    "coordinates": location["coordinates"],
                }
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise DomainError(
                503, "clinic_location_unavailable", "Clinic pickup location is unavailable."
            ) from None
