from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import api as api
from test_api import api_database as api_database

from app.models import Clinic


def test_billing_profile_only_active_clinic_and_scoped_service(api):
    secret = SecretStr("b02-tenant-billing-secret-at-least-32-bytes")
    api.app.state.settings.billing_secret = secret
    tenant = uuid4()
    with Session(api.engine) as session, session.begin():
        session.add(
            Clinic(
                tenant_id=tenant,
                slug="b02-" + str(tenant),
                name="Synthetic",
                status="active",
                membership_provisioned=True,
                primary_color="#156B63",
                description="Synthetic billing test",
                consultation_price_minor=5000,
                commission_bps=1250,
            )
        )
    path = f"/internal/clinics/{tenant}/billing-profile"
    auth = {
        "Authorization": "Bearer " + service_token(secret, "billing", "telelink-tenant-billing")
    }
    assert api.client.get(path).status_code == 401
    assert api.client.get(path, headers=api.user("creator")).status_code == 401
    result = api.client.get(path, headers=auth)
    assert result.status_code == 200 and result.json() == {
        "tenant_id": str(tenant),
        "status": "active",
        "commission_bps": 1250,
    }
    assert (
        api.client.get(f"/internal/clinics/{uuid4()}/billing-profile", headers=auth).status_code
        == 404
    )
    with Session(api.engine) as session, session.begin():
        session.get(Clinic, tenant).status = "suspended"
    assert api.client.get(path, headers=auth).status_code == 409
