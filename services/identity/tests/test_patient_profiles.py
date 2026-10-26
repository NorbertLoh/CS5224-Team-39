from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import api as api
from test_api import api_database as api_database
from test_api import headers
from test_api import signing_key as signing_key

from app.models import Subject

PROFILE = {
    "name": "Synthetic Patient",
    "phone_number": "8123 4567",
    "address_line": "3 Temasek Boulevard",
    "postal_code": "038983",
    "country_code": "SG",
}


def test_self_profile_persists_and_preserves_identity_roles(api):
    path = "/me/patient-profile"
    initial = api.client.get(path, headers=headers(api))
    assert initial.status_code == 200
    assert initial.json()["phone_number"] == ""
    response = api.client.put(path, json=PROFILE, headers=headers(api))
    assert response.status_code == 200, response.text
    expected = PROFILE | {"subject_id": str(api.ids["patient"]), "phone_number": "+6581234567"}
    assert response.json() == expected
    assert response.headers["Cache-Control"] == "no-store"
    assert api.client.get(path, headers=headers(api)).json() == expected
    me = api.client.get("/me", headers=headers(api)).json()
    assert me["display_name"] == PROFILE["name"]
    assert me["global_roles"] == ["patient"]
    other = api.client.get(path, headers=headers(api, "other_patient")).json()
    assert other["address_line"] == "" and other["phone_number"] == ""
    with Session(api.engine) as db:
        subject = db.get(Subject, api.ids["patient"])
        assert subject.email == "patient@example.test"
        assert subject.global_roles == ["patient"]


@pytest.mark.parametrize("actor", ["doctor", "admin_a", "platform"])
def test_nonpatients_cannot_read_or_edit_patient_profile(api, actor):
    assert api.client.get("/me/patient-profile", headers=headers(api, actor)).status_code == 403
    assert (
        api.client.put("/me/patient-profile", json=PROFILE, headers=headers(api, actor)).status_code
        == 403
    )


@pytest.mark.parametrize(
    "change",
    [
        {"name": "  "},
        {"name": "Bad\nname"},
        {"phone_number": "+60123456789"},
        {"phone_number": "12345678"},
        {"address_line": " "},
        {"address_line": "bad\naddress"},
        {"postal_code": "123"},
        {"country_code": "MY"},
        {"subject_id": str(uuid4())},
        {"global_roles": ["platform_admin"]},
        {"email": "other@example.test"},
    ],
)
def test_profile_rejects_invalid_or_privileged_fields(api, change):
    assert (
        api.client.put(
            "/me/patient-profile", json=PROFILE | change, headers=headers(api)
        ).status_code
        == 422
    )
    assert api.client.get("/me/patient-profile", headers=headers(api)).json()["phone_number"] == ""


def test_profile_requires_login_and_service_projection_is_minimal(api):
    assert api.client.get("/me/patient-profile").status_code == 401
    assert api.client.put("/me/patient-profile", json=PROFILE).status_code == 401
    secret = SecretStr("patient-profile-service-secret-at-least-32-bytes")
    api.settings.fulfilment_secret = secret
    auth = {
        "Authorization": "Bearer "
        + service_token(secret, "fulfilment", "telelink-identity-delivery")
    }
    path = f"/internal/patients/{api.ids['patient']}/delivery-contact"
    assert api.client.get(path, headers=headers(api)).status_code == 401
    assert api.client.get(path, headers=auth).status_code == 404
    api.client.put("/me/patient-profile", json=PROFILE, headers=headers(api))
    response = api.client.get(path, headers=auth)
    assert response.status_code == 200
    assert response.json() == {
        "patient_id": str(api.ids["patient"]),
        "name": PROFILE["name"],
        "phone": "+6581234567",
    }
    assert response.headers["Cache-Control"] == "no-store"
    wrong = {"Authorization": "Bearer " + service_token(secret, "fulfilment", "different-purpose")}
    assert api.client.get(path, headers=wrong).status_code == 401
    assert (
        api.client.get(
            f"/internal/patients/{api.ids['other_patient']}/delivery-contact", headers=auth
        ).status_code
        == 404
    )
