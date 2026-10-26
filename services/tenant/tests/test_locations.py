from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token

from app.models import AuditEvent
from tests.test_api import activate, body
from tests.test_api import api as api
from tests.test_api import api_database as api_database

LOCATION = {
    "address_line": "1 Raffles Place",
    "postal_code": "048616",
    "country_code": "SG",
    "coordinates": {"lat": "1.2844", "lng": "103.8511"},
}


def clinic(api):
    response = api.client.post("/clinics", json=body(), headers=api.user())
    assert response.status_code == 201
    return response.json()["tenant_id"]


def test_save_read_audit_and_tenant_role_boundaries(api):
    tenant = clinic(api)
    path = f"/clinics/{tenant}/location"
    assert api.client.get(path, headers=api.user()).json()["location"] is None
    for actor in ("other", "doctor", "platform"):
        assert api.client.put(path, json=LOCATION, headers=api.user(actor)).status_code == 404
        assert api.client.get(path, headers=api.user(actor)).status_code == 404
    assert api.client.put(path, json=LOCATION).status_code == 401
    first = api.client.put(path, json=LOCATION, headers=api.user())
    assert first.status_code == 200, first.text
    assert first.json() == {"tenant_id": tenant, "location": LOCATION}
    assert api.client.get(path, headers=api.user()).json() == first.json()
    assert api.client.put(path, json=LOCATION, headers=api.user()).status_code == 200
    changed = LOCATION | {"address_line": "1 Raffles Place, pickup entrance"}
    assert api.client.put(path, json=changed, headers=api.user()).status_code == 200
    with Session(api.engine) as db:
        events = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == UUID(tenant), AuditEvent.action == "clinic.location_changed"
            )
            .order_by(AuditEvent.occurred_at)
        ).all()
        assert len(events) == 2
        assert events[0].previous_values == {"location": None}
        assert events[1].previous_values == {"location": LOCATION}
        assert events[1].new_values == {"location": changed}
        assert events[1].actor_subject_id == api.ids["creator"]
    api.memberships["creator"][0]["status"] = "revoked"
    assert api.client.put(path, json=LOCATION, headers=api.user()).status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"address_line": "   "},
        {"address_line": "bad\naddress"},
        {"postal_code": "123"},
        {"country_code": "MY"},
        {"coordinates": {"lat": "1.8", "lng": "103.8"}},
        {"coordinates": {"lat": "1.3", "lng": "104.9"}},
        {"tenant_id": "forged"},
    ],
)
def test_location_validation(api, change):
    tenant = clinic(api)
    assert (
        api.client.put(
            f"/clinics/{tenant}/location", json=LOCATION | change, headers=api.user()
        ).status_code
        == 422
    )


def test_internal_location_is_service_only_and_requires_active_clinic(api):
    tenant = clinic(api)
    path = f"/internal/clinics/{tenant}/delivery-location"
    secret = SecretStr("fulfilment-location-secret-32-bytes-minimum")
    api.app.state.settings.fulfilment_secret = secret
    headers = {
        "Authorization": "Bearer " + service_token(secret, "fulfilment", "telelink-tenant-delivery")
    }
    assert api.client.get(path, headers=api.user()).status_code == 401
    assert api.client.get(path).status_code == 401
    assert api.client.get(path, headers=headers).status_code == 409
    activate(api, UUID(tenant))
    assert api.client.get(path, headers=headers).json()["location"] is None
    api.client.put(f"/clinics/{tenant}/location", json=LOCATION, headers=api.user())
    response = api.client.get(path, headers=headers)
    assert response.json() == {"tenant_id": tenant, "location": LOCATION}
    assert response.headers["Cache-Control"] == "no-store"
