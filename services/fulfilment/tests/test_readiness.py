from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from telelink_common.errors import DomainError

from app.main import create_app
from app.models import Order
from app.settings import Settings
from tests.test_api import OTHER_TENANT, create, identity
from tests.test_api import api as api


@pytest.mark.parametrize("paid", [False, True])
def test_readiness_persists_without_payment_or_delivery_and_replays(api, paid):
    client, state, _ = api
    original = create(client).json()
    order_id = UUID(original["order_id"])
    if paid:
        with state.sessions.begin() as db:
            order = db.get(Order, order_id)
            order.status = "paid"
            order.payment_status = "succeeded"
            order.payment_id = uuid4()
    before = client.get(f"/orders/{order_id}").json()
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    path = f"/orders/{order_id}/ready"
    first = client.post(path)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["medicine_status"] == "ready"
    assert result["updated_at"] >= before["updated_at"]
    for field in before.keys() - {"medicine_status", "updated_at"}:
        assert result[field] == before[field]
    assert client.post(path, json={}).json() == result
    with state.sessions() as db:
        stored = db.get(Order, order_id)
        assert stored.medicine_status == "ready"
        assert stored.delivery_id is None
    assert client.get(f"/orders/{order_id}").json() == result
    # Current membership is checked even for a retry of an already-ready order.
    state.identity = identity(roles=(), clinic_role="clinic_admin", active=False)
    assert client.post(path).status_code == 404


@pytest.mark.parametrize(
    "who",
    [
        identity(),
        identity(roles=("platform_admin",)),
        identity(roles=(), clinic_role="doctor"),
        identity(roles=(), clinic_role="clinic_admin", active=False),
        identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT),
    ],
)
def test_readiness_rejects_unauthorised_roles_and_clinics(api, who):
    client, state, _ = api
    order_id = create(client).json()["order_id"]
    state.identity = who
    calls = state.source.calls
    assert client.post(f"/orders/{order_id}/ready").status_code == 404
    assert state.source.calls == calls
    with state.sessions() as db:
        assert db.get(Order, UUID(order_id)).medicine_status == "not_ready"


@pytest.mark.parametrize(
    "status", ["cancelled", "exception", "submitting", "dispatched", "delivered"]
)
@pytest.mark.parametrize("ready", [False, True])
def test_readiness_rejects_inactive_orders_even_on_retry(api, status, ready):
    client, state, _ = api
    order_id = UUID(create(client).json()["order_id"])
    with state.sessions.begin() as db:
        order = db.get(Order, order_id)
        order.status = status
        order.medicine_status = "ready" if ready else "not_ready"
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    response = client.post(f"/orders/{order_id}/ready")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "order_not_active"


@pytest.mark.parametrize("payment_status", ["refund_required", "refunded"])
def test_refunded_order_cannot_be_marked_ready(api, payment_status):
    client, state, _ = api
    order_id = UUID(create(client).json()["order_id"])
    with state.sessions.begin() as db:
        db.get(Order, order_id).payment_status = payment_status
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert client.post(f"/orders/{order_id}/ready").status_code == 409


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("status", "voided", 409),
        ("status", "draft", 409),
        ("tenant_id", uuid4(), 404),
        ("patient_id", uuid4(), 404),
        ("appointment_id", uuid4(), 404),
    ],
)
def test_readiness_checks_issued_prescription_context_and_rolls_back(api, field, value, code):
    client, state, _ = api
    original = create(client).json()
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    state.source.context = state.source.context.model_copy(update={field: value})
    assert client.post(f"/orders/{original['order_id']}/ready").status_code == code
    assert client.get(f"/orders/{original['order_id']}").json() == original


def test_unavailable_source_fails_closed_then_retry_succeeds(api):
    client, state, _ = api
    original = create(client).json()
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    state.source.error = DomainError(503, "unavailable", "Upstream unavailable.")
    path = f"/orders/{original['order_id']}/ready"
    assert client.post(path).status_code == 503
    assert client.get(f"/orders/{original['order_id']}").json() == original
    state.source.error = None
    assert client.post(path).status_code == 200


def test_concurrent_readiness_is_one_durable_transition(api):
    client, state, _ = api
    order_id = create(client).json()["order_id"]
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: client.post(f"/orders/{order_id}/ready"), range(6)))
    assert all(result.status_code == 200 for result in results)
    assert all(result.json() == results[0].json() for result in results)
    assert client.get(f"/orders/{order_id}").json() == results[0].json()


@pytest.mark.parametrize(
    "body", [{"medicine_status": "ready"}, {"tenant_id": str(OTHER_TENANT)}, []]
)
def test_readiness_rejects_client_controlled_fields(api, body):
    client, state, _ = api
    order_id = create(client).json()["order_id"]
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert client.post(f"/orders/{order_id}/ready", json=body).status_code == 422
    assert client.get(f"/orders/{order_id}").json()["medicine_status"] == "not_ready"


def test_readiness_missing_order_and_authentication(api):
    client, state, _ = api
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert client.post(f"/orders/{uuid4()}/ready").status_code == 404
    with TestClient(create_app(Settings(environment="test", database_url=None))) as unauthenticated:
        assert unauthenticated.post(f"/orders/{uuid4()}/ready").status_code == 401
