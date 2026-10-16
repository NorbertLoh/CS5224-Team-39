from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import api as api
from test_api import api_database as api_database

from app.models import Clinic


def test_document_clinic_service_scope_and_inactive_historical_clinic(api):
    key = SecretStr("records-tenant-document-key-at-least-32-bytes")
    api.app.state.settings.records_secret = key
    tenant = uuid4()
    with Session(api.engine) as session, session.begin():
        session.add(
            Clinic(
                tenant_id=tenant,
                slug="p02-" + str(tenant),
                name="Synthetic Clinic",
                status="suspended",
                primary_color="#156B63",
                description="Synthetic document test",
                consultation_price_minor=2500,
            )
        )
    path = f"/internal/clinics/{tenant}/document-profile"
    assert api.client.get(path, headers=api.user("creator")).status_code == 401
    auth = {
        "Authorization": "Bearer "
        + service_token(key, "clinical-records", "telelink-tenant-document")
    }
    response = api.client.get(path, headers=auth)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"tenant_id": str(tenant), "clinic_name": "Synthetic Clinic"}
    assert (
        api.client.get(f"/internal/clinics/{uuid4()}/document-profile", headers=auth).status_code
        == 404
    )
