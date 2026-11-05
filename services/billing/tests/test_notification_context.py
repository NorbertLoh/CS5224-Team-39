from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware
from telelink_common.service_auth import service_token

from app.api.notification_context import router
from app.database import get_session
from app.settings import Settings


def test_refund_notice_requires_current_success_and_correct_tenant():
    payment, tenant, patient, refund = (uuid4() for _ in range(4))
    row = SimpleNamespace(
        tenant_id=tenant,
        patient_id=patient,
        appointment_id=uuid4(),
        order_id=None,
        amount_minor=3500,
        currency="SGD",
        status="refund_pending",
    )
    attempt = SimpleNamespace(status="pending")
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, service="billing")
    key = SecretStr("billing-notification-" + "x" * 40)
    app.state.settings = Settings(_env_file=None, notification_secret=key)
    app.include_router(router)
    install_error_handlers(app)
    app.dependency_overrides[get_session] = lambda: SimpleNamespace(
        get=lambda *args: row, scalar=lambda *args: attempt
    )
    path = (
        f"/internal/payments/{payment}/notification-context?tenant_id={tenant}&refund_id={refund}"
    )
    headers = {
        "Authorization": "Bearer "
        + service_token(key, "notification", "telelink-billing-notification")
    }
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert (
            client.get(path.replace(str(tenant), str(uuid4())), headers=headers).status_code == 404
        )
        assert client.get(path, headers=headers).json()["eligible"] is False
        row.status, attempt.status = "refunded", "succeeded"
        response = client.get(path, headers=headers)
        assert response.json()["eligible"] is True
        assert response.json()["patient_id"] == str(patient)
        assert response.headers["cache-control"] == "no-store"
