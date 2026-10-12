import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.logging import JsonFormatter, request_id_context
from app.main import create_app
from app.settings import Settings


def test_settings_environment_and_validation(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "scheduling")
    monkeypatch.setenv("SERVICE_PORT", "8100")
    monkeypatch.setenv("SERVICE_ENVIRONMENT", "production")
    settings = Settings(_env_file=None)
    assert (settings.name, settings.port, settings.expose_docs) == ("scheduling", 8100, False)
    assert Settings(_env_file=None, docs_enabled=True).expose_docs
    monkeypatch.setenv("SERVICE_PORT", "70000")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_health_lifecycle_and_openapi():
    app = create_app(Settings(_env_file=None))
    # TestClient without its context manager deliberately does not run lifespan.
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "alive", "service": "template"}
        assert client.get("/health/ready").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "/health/ready" in schema["paths"]
    assert not app.state.ready
    client = TestClient(app)
    try:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
    finally:
        client.close()


def test_docs_disabled_in_production():
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.get("/health/live").status_code == 200


def test_correlation_and_logs_omit_payloads(caplog):
    app = create_app(Settings(_env_file=None))

    @app.get("/patients/{patient_id}")
    async def patient(patient_id: str):
        return {"ok": True}

    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="telelink.request"):
        response = client.get(
            "/patients/private-patient?secret=private-secret",
            headers={"x-request-id": "demo-123", "authorization": "secret-token"},
        )
        assert response.headers["x-request-id"] == "demo-123"
        record = caplog.records[-1]
        payload = json.loads(JsonFormatter().format(record))
        assert payload["route"] == "/patients/{patient_id}"
        assert payload["request_id"] == "demo-123"
        assert payload["status_code"] == 200
        assert "private-patient" not in json.dumps(payload)
        assert "private-secret" not in json.dumps(payload)
        assert "secret-token" not in json.dumps(payload)
        invalid = client.get("/health/live", headers={"x-request-id": "invalid id"})
        assert invalid.headers["x-request-id"] != "invalid id"
    assert request_id_context.get() is None


def test_unhandled_error_logged_without_sensitive_exception(caplog):
    app = create_app(Settings(_env_file=None))

    @app.get("/fail")
    async def fail():
        raise RuntimeError("private clinical payload")

    with TestClient(app, raise_server_exceptions=False) as client:
        with caplog.at_level(logging.INFO, logger="telelink.request"):
            assert client.get("/fail").status_code == 500
        payload = json.loads(JsonFormatter().format(caplog.records[-1]))
        assert payload["status_code"] == 500
        assert "private clinical payload" not in json.dumps(payload)
    assert request_id_context.get() is None
