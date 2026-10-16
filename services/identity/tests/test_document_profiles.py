from uuid import uuid4

from pydantic import SecretStr
from telelink_common.service_auth import service_token
from test_api import api as api
from test_api import api_database as api_database
from test_api import signing_key as signing_key


def test_document_participants_service_scope_and_minimum_fields(api):
    key = SecretStr("records-identity-document-key-at-least-32-bytes")
    api.settings.records_secret = key
    path = "/internal/document-participants"
    params = {"patient_id": str(api.ids["patient"]), "doctor_id": str(api.ids["doctor"])}
    user = {"Authorization": "Bearer " + api.mint("patient")}
    assert api.client.get(path, params=params, headers=user).status_code == 401
    auth = {
        "Authorization": "Bearer "
        + service_token(key, "clinical-records", "telelink-identity-document")
    }
    response = api.client.get(path, params=params, headers=auth)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"patient_id", "patient_name", "doctor_id", "doctor_name"}
    assert (
        api.client.get(path, params=params | {"patient_id": str(uuid4())}, headers=auth).status_code
        == 404
    )
