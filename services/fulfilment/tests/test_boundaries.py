import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from telelink_common.access import IdentityClient
from telelink_common.errors import DomainError

from app.database import get_session
from app.dispensing import DispensingContext, FixtureDispensing, UnavailableDispensing
from app.main import create_app
from app.models import Order
from app.schemas import Money
from app.settings import Settings
from tests.test_api import TENANT, Source, context, identity


def test_fixture_projects_only_minimum_context():
    path = Path(__file__).resolve().parents[3] / "contracts/examples/prescription-order-quote.json"
    source = FixtureDispensing(path)
    context = source.context
    result = source.get(context.prescription_id, context.patient_id, "test")
    assert result.status == "issued" and result.items[0].quantity == 2
    assert "instructions" not in result.model_dump_json()
    assert "doctor_id" not in result.model_dump_json()
    with pytest.raises(DomainError) as error:
        source.get(context.prescription_id, uuid4(), "test")
    assert error.value.status_code == 404
    with pytest.raises(DomainError):
        UnavailableDispensing().get(uuid4(), uuid4(), "test")
    raw = result.model_dump()
    raw["items"] *= 2
    with pytest.raises(ValidationError):
        DispensingContext.model_validate(raw)


def test_fail_closed_configuration_and_required_currency():
    with pytest.raises(ValidationError):
        Settings(environment="production", dispensing_fixture_path="example.json")
    with pytest.raises(ValidationError):
        Settings(cursor_secret="short")
    with pytest.raises(ValidationError):
        Money(amount_minor=10)
    with TestClient(create_app(Settings(database_url=None))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_real_jwt_and_identity_revocation_path(sessions):
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        environment="test",
        database_url=None,
        auth_issuer="http://localhost/pool",
        auth_jwks_url="http://localhost/pool/jwks",
        auth_client_id="web",
        identity_url="http://identity.test",
    )
    app = create_app(settings)
    payload = identity(roles=(), clinic_role="clinic_admin").model_dump(mode="json")
    forwarded = []

    def lookup(request):
        forwarded.append(request.headers["Authorization"])
        return httpx.Response(200, json=payload)

    app.state.identity_client.close()
    app.state.identity_client = IdentityClient(settings, transport=httpx.MockTransport(lookup))
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update(kid="key", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session
    order_id = uuid4()
    app.state.dispensing = Source()
    prescription = context()
    with sessions.begin() as db:
        db.add(
            Order(
                order_id=order_id,
                tenant_id=prescription.tenant_id,
                prescription_id=prescription.prescription_id,
                patient_id=prescription.patient_id,
                appointment_id=prescription.appointment_id,
                medication_subtotal_minor=0,
            )
        )

    def headers(**changes):
        token = jwt.encode(
            dict(
                sub=payload["cognito_sub"],
                iss=settings.auth_issuer,
                iat=int(time.time()),
                exp=int(time.time()) + 300,
                token_use="access",
                client_id="web",
            )
            | changes,
            signing_key,
            algorithm="RS256",
            headers={"kid": "key"},
        )
        return {"Authorization": "Bearer " + token}

    path = f"/clinics/{TENANT}/catalogue"
    ready_path = f"/orders/{order_id}/ready"
    with TestClient(app) as client:
        assert client.get(path, headers=headers()).status_code == 200
        assert client.post(ready_path, headers=headers()).status_code == 200
        assert forwarded
        assert client.get(path, headers=headers(exp=1)).status_code == 401
        assert client.get(path, headers=headers(token_use="id")).status_code == 401
        assert client.get(path, headers={"X-Role": "clinic_admin"}).status_code == 401
        assert client.post(ready_path, headers=headers(exp=1)).status_code == 401
        assert client.post(ready_path, headers=headers(token_use="id")).status_code == 401
        assert client.post(ready_path, headers={"X-Role": "clinic_admin"}).status_code == 401
        payload["memberships"][0]["status"] = "revoked"
        assert client.post(ready_path, headers=headers()).status_code == 404
        response = client.get(path, headers=headers(**{"cognito:groups": ["clinic_admin"]}))
        assert response.status_code == 404
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        payload["cognito_sub"] = "other-subject"
        assert client.get(path, headers=headers(sub="original-subject")).status_code == 502
