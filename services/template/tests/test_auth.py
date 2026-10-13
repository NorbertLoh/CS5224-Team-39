import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError
from pydantic import ValidationError

from app.main import create_app
from app.settings import Settings


@pytest.fixture
def auth():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    settings = Settings(
        _env_file=None, environment="test", auth_issuer="http://localhost:4566/pool",
        auth_jwks_url="http://localhost:4566/pool/.well-known/jwks.json",
        auth_client_id="web", auth_required_scopes="openid",
    )
    app = create_app(settings)
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def mint(**changes):
        claims = dict(sub="patient", iss=settings.auth_issuer, exp=int(time.time()) + 300,
                      iat=int(time.time()), token_use="access", client_id="web", scope="openid")
        return jwt.encode(claims | changes, key, algorithm="RS256", headers={"kid": "test-key"})

    with TestClient(app) as client:
        yield client, mint, app


def probe(client, token):
    return client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})


def test_access_token_and_missing_auth(auth):
    client, mint, _ = auth
    assert client.get("/auth/session").status_code == 401
    assert client.get("/auth/session", headers={"x-user-id": "patient"}).status_code == 401
    assert probe(client, mint()).json() == {"subject": "patient", "scopes": ["openid"]}


@pytest.mark.parametrize("changes", [
    {"iss": "http://localhost:4566/other"}, {"client_id": "other"}, {"token_use": "id"},
    {"exp": 1}, {"exp": None}, {"iat": int(time.time()) + 3600}, {"sub": ""},
])
def test_rejected_claims(auth, changes):
    client, mint, _ = auth
    response = probe(client, mint(**changes))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_signature_and_algorithm(auth):
    client, mint, _ = auth
    forged = jwt.encode({"sub": "patient"}, "untrusted" * 4, algorithm="HS256",
                        headers={"kid": "test-key"})
    assert probe(client, forged).status_code == 401
    header, body, signature = mint().split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert probe(client, f"{header}.{body}.{signature}").status_code == 401


def test_missing_scope(auth):
    client, mint, _ = auth
    assert probe(client, mint(scope="email")).status_code == 403


def test_unavailable_keys(auth):
    client, mint, app = auth

    def unavailable_keys():
        raise PyJWKClientConnectionError("offline")

    app.state.token_verifier.jwks = PyJWKClient("http://localhost:4566/missing")
    app.state.token_verifier.jwks.fetch_data = unavailable_keys
    assert probe(client, mint()).status_code == 503


def test_configuration_fails_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert probe(client, "any").status_code == 503
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_client_id="web")
    for environment in ("development", "demo", "production"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, environment=environment, auth_client_id="web",
                     auth_issuer="http://localhost:4566/pool",
                     auth_jwks_url="http://floci:4566/pool/.well-known/jwks.json")
