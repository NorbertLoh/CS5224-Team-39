from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware
from telelink_common.service_auth import service_token

from app.api.notification_context import router
from app.database import get_session
from app.settings import Settings

KEY = "notification-test-independent-key-at-least-32-bytes"


def test_notification_key_validation():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, notification_secret="short")


@pytest.fixture
def context_api():
    resource, tenant, patient = uuid4(), uuid4(), uuid4()
    row = SimpleNamespace(
        subject_id=patient,
        global_roles=["patient"],
        email="patient@example.test",
        appointment_id=resource,
        document_id=resource,
        delivery_id=resource,
        order_id=uuid4(),
        patient_id=patient,
        tenant_id=tenant,
        status="ready",
        prescription_id=uuid4(),
        medical_certificate_id=None,
        private_body="must not leak",
    )
    order = SimpleNamespace(
        tenant_id=tenant, patient_id=patient, order_id=row.order_id, delivery_id=resource
    )

    class DB:
        def get(self, model, key):
            if model.__name__ == "Order":
                return order
            return row if key in {resource, patient} else None

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, service="document")
    app.state.settings = Settings(_env_file=None, notification_secret=KEY)
    app.include_router(router)
    install_error_handlers(app)
    app.dependency_overrides[get_session] = lambda: DB()
    with TestClient(app) as client:
        yield client, row, tenant, patient, resource


@pytest.mark.parametrize("auth", ["missing", "wrong_caller", "wrong_audience", "valid"])
def test_auth_and_minimal_projection(context_api, auth):
    client, row, tenant, patient, resource = context_api
    SERVICE = "document"
    if SERVICE == "scheduling":
        row.status = "confirmed"
    if SERVICE == "fulfilment":
        row.status = "submitted"
    path = (
        f"/internal/notification-recipients/{patient}"
        if SERVICE == "identity"
        else f"/internal/documents/{resource}/notification-context?tenant_id={tenant}"
    )
    headers = {}
    if auth != "missing":
        token = service_token(
            SecretStr(KEY),
            "wrong" if auth == "wrong_caller" else "notification",
            "wrong" if auth == "wrong_audience" else f"telelink-{SERVICE}-notification",
        )
        headers = {"Authorization": "Bearer " + token}
    response = client.get(path, headers=headers)
    assert response.status_code == (200 if auth == "valid" else 401)
    if auth == "valid":
        assert response.headers["Cache-Control"] == "no-store"
        assert "private_body" not in response.json()
        if SERVICE == "identity":
            assert response.json() == {"recipient_id": str(patient), "email": row.email}
        else:
            assert response.json()["patient_id"] == str(patient)
            assert response.json()["eligible"] is True
            assert "email" not in response.json()


def test_tenant_or_patient_guard(context_api):
    client, row, tenant, patient, resource = context_api
    SERVICE = "document"
    headers = {
        "Authorization": "Bearer "
        + service_token(SecretStr(KEY), "notification", f"telelink-{SERVICE}-notification")
    }
    if SERVICE == "identity":
        row.global_roles = ["platform_admin"]
        path = f"/internal/notification-recipients/{patient}"
    else:
        path = f"/internal/documents/{resource}/notification-context?tenant_id={uuid4()}"
    assert client.get(path, headers=headers).status_code == 404
