"""Registration must persist complete pickup settings before provisioning."""

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Clinic, ClinicLocation
from app.schemas import ClinicCreate
from tests.test_api import PICKUP_LOCATION, body
from tests.test_api import api as api
from tests.test_api import api_database as api_database


@pytest.mark.parametrize("field", ["address_line", "postal_code", "coordinates", "pickup_contact"])
def test_registration_requires_all_pickup_fields(field):
    location = PICKUP_LOCATION.copy()
    del location[field]
    with pytest.raises(ValidationError):
        ClinicCreate.model_validate(body(location=location))


@pytest.mark.parametrize(
    "change",
    [
        {"address_line": "   "},
        {"postal_code": "123"},
        {"coordinates": {"lat": "1.8", "lng": "103.8"}},
        {"pickup_contact": None},
        {"pickup_contact": {"name": "   ", "phone": "81234567"}},
        {"pickup_contact": {"name": "Desk", "phone": "+60123456789"}},
        {"pickup_contact": {"name": "Desk"}},
        {"pickup_contact": {"phone": "81234567"}},
    ],
)
def test_registration_validates_pickup_settings(change):
    with pytest.raises(ValidationError):
        ClinicCreate.model_validate(body(location=PICKUP_LOCATION | change))


def test_registration_rejects_missing_location():
    payload = body()
    del payload["location"]
    with pytest.raises(ValidationError):
        ClinicCreate.model_validate(payload)


def test_registration_normalizes_pickup_contact():
    location = PICKUP_LOCATION | {
        "pickup_contact": {"name": "  Pickup desk  ", "phone": "8123 4567"}
    }
    parsed = ClinicCreate.model_validate(body(location=location))
    assert parsed.location.pickup_contact.name == "Pickup desk"
    assert parsed.location.pickup_contact.phone == "+6581234567"


def test_invalid_registration_creates_no_clinic_or_membership(api):
    payload = body(location=PICKUP_LOCATION | {"pickup_contact": None})
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 422
    assert api.state["calls"] == 0
    with Session(api.engine) as db:
        assert db.scalar(select(Clinic).where(Clinic.slug == payload["slug"])) is None


def test_registration_location_survives_provisioning_failure_and_retry(api):
    payload = body()
    api.state["fail"] = True
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 503
    with Session(api.engine) as db:
        clinic = db.scalar(select(Clinic).where(Clinic.slug == payload["slug"]))
        tenant_id = clinic.tenant_id
        assert db.get(ClinicLocation, tenant_id).location == PICKUP_LOCATION
    api.state["fail"] = False
    changed = payload | {"location": PICKUP_LOCATION | {"address_line": "Another entrance"}}
    assert api.client.post("/clinics", json=changed, headers=api.user()).status_code == 409
    response = api.client.post("/clinics", json=payload, headers=api.user())
    assert response.status_code == 200
    assert UUID(response.json()["tenant_id"]) == tenant_id
    path = f"/clinics/{tenant_id}/location"
    assert api.client.get(path, headers=api.user()).json()["location"] == PICKUP_LOCATION
    edited = PICKUP_LOCATION | {"address_line": "New pickup entrance"}
    assert api.client.put(path, json=edited, headers=api.user()).status_code == 200
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 200
    assert api.client.get(path, headers=api.user()).json()["location"] == edited
    with Session(api.engine) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)).all()
        assert len(events) == 2
        assert any(event.previous_values == {"location": None} for event in events)
        assert all(event.actor_subject_id == api.ids["creator"] for event in events)
