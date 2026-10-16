from types import SimpleNamespace

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from telelink_common.service_auth import require_service, service_token

KEY = SecretStr("service-document-secret-for-tests-32-bytes")


@pytest.fixture
def client():
    app = FastAPI()
    app.state.settings = SimpleNamespace(document_secret=KEY)

    @app.get(
        "/private",
        dependencies=[
            Depends(require_service("document", "telelink-records-document", "document_secret"))
        ],
    )
    def private():
        return {"ok": True}

    with TestClient(app) as client:
        yield client


def test_short_lived_service_credentials_and_missing_configuration(client):
    token = service_token(KEY, "document", "telelink-records-document")
    assert client.get("/private", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert client.get("/private").status_code == 401
    client.app.state.settings.document_secret = None
    assert client.get("/private", headers={"Authorization": "Bearer " + token}).status_code == 503


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": "other"},
        {"iss": "telelink-service:other"},
        {"aud": "another-purpose"},
        {"aud": ["telelink-records-document"]},
        {"exp": 0},
        {"exp": True},
        {"iat": False},
        {"exp": "2000000000"},
        {"iat": 0},
    ],
)
def test_reject_wrong_caller_purpose_and_invalid_lifetime(client, changes):
    claims = jwt.decode(
        service_token(KEY, "document", "telelink-records-document"),
        KEY.get_secret_value(),
        algorithms=["HS256"],
        audience="telelink-records-document",
    )
    token = jwt.encode(claims | changes, KEY.get_secret_value(), algorithm="HS256")
    assert client.get("/private", headers={"Authorization": "Bearer " + token}).status_code == 401
