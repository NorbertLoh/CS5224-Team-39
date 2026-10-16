import json
import time
from uuid import UUID

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends
from fastapi.testclient import TestClient
from telelink_common.access import IdentityClient, require_global_role

from app.main import create_app
from app.settings import Settings

TENANT = UUID("00000000-0000-4000-8000-000000000002")
OTHER = UUID("00000000-0000-4000-8000-000000000025")
PATH = f"/clinics/{TENANT}/access"


@pytest.fixture
def access():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        _env_file=None,
        environment="test",
        auth_issuer="http://localhost/pool",
        auth_jwks_url="http://localhost/pool/.well-known/jwks.json",
        auth_client_id="web",
        identity_url="http://identity.test",
        database_url=None,
    )
    payload = {
        "subject_id": "00000000-0000-4000-8000-000000000003",
        "cognito_sub": "current-sub",
        "display_name": "Synthetic",
        "global_roles": ["patient"],
        "memberships": [
            {
                "membership_id": "00000000-0000-4000-8000-000000000005",
                "subject_id": "00000000-0000-4000-8000-000000000003",
                "tenant_id": str(TENANT),
                "roles": ["clinic_admin"],
                "status": "active",
                "created_at": "2026-10-13T01:00:00.000Z",
                "updated_at": "2026-10-13T01:00:00.000Z",
            }
        ],
    }
    app = create_app(settings)
    app.state.identity_client.close()
    app.state.identity_client = IdentityClient(
        settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="key", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def headers(**claims):
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": "current-sub",
                "iss": settings.auth_issuer,
                "iat": now,
                "exp": now + 300,
                "token_use": "access",
                "client_id": "web",
            }
            | claims,
            key,
            algorithm="RS256",
            headers={"kid": "key"},
        )
        return {"Authorization": "Bearer " + token}

    @app.get("/patient-probe")
    def patient_probe(identity=Depends(require_global_role("patient"))):
        return {"subject_id": str(identity.subject_id)}

    with TestClient(app) as client:
        yield client, payload, headers


def test_endpoint_uses_current_active_membership_not_headers_or_groups(access):
    client, payload, headers = access
    assert (
        client.get(
            PATH, headers={"X-User-ID": payload["subject_id"], "X-Role": "clinic_admin"}
        ).status_code
        == 401
    )
    assert client.get(PATH, headers=headers()).status_code == 200
    assert client.get(f"/clinics/{OTHER}/access", headers=headers()).status_code == 404
    payload["memberships"][0]["status"] = "revoked"
    response = client.get(
        PATH, headers=headers(**{"cognito:groups": ["clinic_admin", "platform_admin"]})
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    payload["memberships"] = []
    payload["global_roles"] = ["platform_admin"]
    assert client.get(PATH, headers=headers()).status_code == 200


def test_global_role_and_identity_subject_binding(access):
    client, payload, headers = access
    assert client.get("/patient-probe", headers=headers()).status_code == 200
    payload["global_roles"] = []
    assert (
        client.get("/patient-probe", headers=headers(**{"cognito:groups": ["patient"]})).status_code
        == 403
    )
    payload["cognito_sub"] = "other-subject"
    assert client.get(PATH, headers=headers()).status_code == 502


def test_expired_tokens_and_invalid_tenant_ids_are_rejected(access):
    client, _, headers = access
    assert client.get(PATH, headers=headers(exp=1)).status_code == 401
    response = client.get("/clinics/invalid/access", headers=headers())
    assert response.status_code == 422
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
