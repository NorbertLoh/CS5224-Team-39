from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from telelink_common.access import ClinicMembership, CurrentIdentity, require_identity
from telelink_common.errors import DomainError

from app.database import get_session
from app.dispensing import DispensingContext
from app.main import create_app
from app.models import CatalogueItem, Order, OrderRequest
from app.settings import Settings

TENANT, OTHER_TENANT, PATIENT, OTHER_PATIENT, MEDICATION, RX, APPOINTMENT, ITEM = [
    uuid4() for _ in range(8)
]
NOW = datetime.now(timezone.utc)


def identity(subject=PATIENT, roles=("patient",), clinic_role=None, tenant=TENANT, active=True):
    return CurrentIdentity(
        subject_id=subject,
        cognito_sub=str(subject),
        display_name="Synthetic test user",
        global_roles=list(roles),
        memberships=[]
        if clinic_role is None
        else [
            ClinicMembership(
                membership_id=uuid4(),
                subject_id=subject,
                tenant_id=tenant,
                roles=[clinic_role],
                status="active" if active else "revoked",
                created_at=NOW,
                updated_at=NOW,
            )
        ],
    )


def context(**changes):
    return DispensingContext.model_validate(
        dict(
            prescription_id=RX,
            appointment_id=APPOINTMENT,
            tenant_id=TENANT,
            patient_id=PATIENT,
            status="issued",
            items=[dict(prescription_item_id=ITEM, medication_id=MEDICATION, quantity=2)],
        )
        | changes
    )


class Source:
    def __init__(self):
        self.context = context()
        self.calls = 0
        self.error = None

    def get(self, prescription_id, patient_id, request_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.context.model_copy(update={"prescription_id": prescription_id})


@pytest.fixture
def api(sessions):
    app = create_app(Settings(environment="test", database_url=None, cursor_secret="c" * 32))
    state = SimpleNamespace(identity=identity(), source=Source(), sessions=sessions)
    app.dependency_overrides[require_identity] = lambda: state.identity

    def session():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session
    app.state.dispensing = state.source
    with sessions.begin() as db:
        db.add(
            CatalogueItem(
                tenant_id=TENANT,
                medication_id=MEDICATION,
                display_name="Synthetic medicine",
                unit_label="demo unit",
                unit_price_minor=1234,
                active=True,
            )
        )
    with TestClient(app) as client:
        yield client, state, app


def create(client, key="test-key", rx=RX, **extra):
    return client.post(
        "/orders", json={"prescription_id": str(rx)} | extra, headers={"Idempotency-Key": key}
    )


def test_create_trusted_snapshots_replay_and_new_key(api):
    client, state, _ = api
    first = create(client)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["medication_subtotal"] == {"amount_minor": 2468, "currency": "SGD"}
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["unit_price"]["amount_minor"] == 1234
    assert body["items"][0]["line_total"]["amount_minor"] == 2468
    assert body["status"] == "awaiting_payment"
    assert body["medicine_status"] == "not_ready"
    assert body["payment_status"] == "unpaid"
    assert all(
        body[key] is None
        for key in ("payment_id", "quote_id", "delivery_id", "delivery_fee", "total")
    )
    assert body["created_at"].endswith("Z")
    assert "instructions" not in first.text
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = 9999
        db.get(Order, UUID(body["order_id"])).status = "cancelled"
    replay = create(client)
    assert replay.status_code == 200 and replay.json() == body
    existing = create(client, key="new-key")
    assert existing.status_code == 200
    assert existing.json()["order_id"] == body["order_id"]
    assert existing.json()["status"] == "cancelled"
    assert existing.json()["medication_subtotal"]["amount_minor"] == 2468
    assert state.source.calls == 1
    assert create(client, rx=uuid4()).status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", 1),
        ("tenant_id", str(OTHER_TENANT)),
        ("patient_id", str(OTHER_PATIENT)),
        ("total", {"amount_minor": 1, "currency": "SGD"}),
        ("items", []),
    ],
)
def test_create_rejects_browser_authority(api, field, value):
    assert create(api[0], **{field: value}).status_code == 422
    assert api[1].source.calls == 0


@pytest.mark.parametrize("key", ["", "a" * 65, "bad key", "bad/key", "bad@key"])
def test_key_validation(api, key):
    assert create(api[0], key=key).status_code == 422


def test_missing_key_and_no_auth(sessions):
    app = create_app(Settings(environment="test", database_url=None))
    with TestClient(app) as client:
        assert client.get("/orders").status_code == 401
        assert client.post("/orders", json={"prescription_id": str(RX)}).status_code == 401
        assert client.put(f"/clinics/{TENANT}/catalogue/{MEDICATION}", json={}).status_code == 401


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"status": "draft"}, 409),
        ({"status": "voided"}, 409),
        ({"patient_id": OTHER_PATIENT}, 404),
        ({"tenant_id": OTHER_TENANT}, 409),
    ],
)
def test_prescription_validation(api, changes, code):
    client, state, _ = api
    state.source.context = context(**changes)
    response = create(client)
    assert response.status_code == code, response.text
    with state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0
        assert db.scalar(select(func.count()).select_from(OrderRequest)) == 0


def test_unavailable_and_inactive_catalogue(api):
    client, state, _ = api
    state.source.error = DomainError(503, "unavailable", "Upstream unavailable.")
    assert create(client).status_code == 503
    state.source.error = None
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).active = False
    response = create(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "medication_unavailable"
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).active = True
    assert create(client).status_code == 201  # failed request never consumes key


def test_amount_overflow(api):
    client, state, _ = api
    with state.sessions.begin() as db:
        db.get(CatalogueItem, (TENANT, MEDICATION)).unit_price_minor = 9007199254740991
    response = create(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "amount_out_of_range"


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_creation(api, same_key):
    client, state, _ = api
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda i: create(client, key="same" if same_key else f"key-{i}"), range(6))
        )
    assert sorted(result.status_code for result in results) == [200] * 5 + [201]
    assert len({result.json()["order_id"] for result in results}) == 1
    with state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.scalar(select(func.count()).select_from(OrderRequest)) == (1 if same_key else 6)
    assert state.source.calls == 1


def test_same_key_concurrent_different_body(api):
    client, state, _ = api
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda rx: create(client, rx=rx), [RX, uuid4()]))
    assert sorted(result.status_code for result in results) == [201, 409]
    with state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1


@pytest.mark.parametrize(
    "who,allowed",
    [
        (identity(), True),
        (identity(subject=OTHER_PATIENT), False),
        (identity(subject=OTHER_PATIENT, roles=(), clinic_role="clinic_admin"), True),
        (identity(roles=(), clinic_role="clinic_admin", active=False), False),
        (identity(roles=(), clinic_role="clinic_admin", tenant=OTHER_TENANT), False),
        (identity(roles=(), clinic_role="doctor"), False),
        (identity(roles=("platform_admin",)), True),
    ],
)
def test_order_access(api, who, allowed):
    client, state, _ = api
    order_id = create(client).json()["order_id"]
    state.identity = who
    response = client.get(f"/orders/{order_id}")
    assert (response.status_code == 200) == allowed
    if who.global_roles == ["platform_admin"]:
        assert "items" not in response.json()
        assert "Synthetic medicine" not in response.text
    listing = client.get("/orders")
    assert (listing.status_code == 200 and len(listing.json()["items"]) == 1) == allowed
    if who.global_roles == ["platform_admin"]:
        assert "items" not in listing.json()["items"][0]


def test_other_patient_cannot_reuse_prescription_and_nonpatient_cannot_create(api):
    client, state, _ = api
    create(client)
    state.identity = identity(subject=OTHER_PATIENT)
    assert create(client, key="other").status_code == 404
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert create(client).status_code == 403


def catalogue_body(**changes):
    return (
        dict(
            display_name="Synthetic changed",
            unit_label="demo unit",
            unit_price={"amount_minor": 2000, "currency": "SGD"},
            active=True,
        )
        | changes
    )


def test_catalogue_admin_write_doctor_read_and_tenant_isolation(api):
    client, state, _ = api
    path = f"/clinics/{TENANT}/catalogue"
    assert client.get(path).status_code == 404
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    response = client.put(f"{path}/{MEDICATION}", json=catalogue_body())
    assert response.status_code == 200
    assert response.json()["unit_price"]["amount_minor"] == 2000
    assert response.json()["updated_at"].endswith("Z")
    assert client.put(f"{path}/{uuid4()}", json=catalogue_body(active=False)).status_code == 201
    assert len(client.get(path).json()["items"]) == 1
    assert client.get(f"/clinics/{OTHER_TENANT}/catalogue").status_code == 404
    state.identity = identity(roles=(), clinic_role="doctor")
    assert client.get(path).status_code == 200
    assert client.put(f"{path}/{MEDICATION}", json=catalogue_body()).status_code == 404
    state.identity = identity(roles=(), clinic_role="doctor", active=False)
    assert client.get(path).status_code == 404
    state.identity = identity(roles=("platform_admin",))
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"unit_price": {"amount_minor": -1, "currency": "SGD"}},
        {"unit_price": {"amount_minor": True, "currency": "SGD"}},
        {"unit_price": {"amount_minor": 1.5, "currency": "SGD"}},
        {"unit_price": {"amount_minor": 1, "currency": "USD"}},
        {"unit_price": {"amount_minor": 9007199254740992, "currency": "SGD"}},
        {"display_name": "   "},
        {"unit_label": " "},
        {"active": "true"},
        {"tenant_id": str(TENANT)},
    ],
)
def test_catalogue_invalid_inputs(api, changes):
    client, state, _ = api
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    assert (
        client.put(
            f"/clinics/{TENANT}/catalogue/{MEDICATION}", json=catalogue_body(**changes)
        ).status_code
        == 422
    )


@pytest.mark.parametrize("equal_times", [False, True])
def test_newest_order_pagination_and_sort_scope(api, equal_times):
    client, state, _ = api
    ids = []
    for _ in range(3):
        rx = uuid4()
        result = create(client, key=str(rx), rx=rx)
        assert result.status_code == 201
        ids.append(result.json()["order_id"])
    # Equal timestamps exercise the ID tie-breaker at every page boundary.
    if equal_times:
        with state.sessions.begin() as db:
            for row in db.scalars(select(Order)):
                row.created_at = NOW
    expected = sorted(ids, reverse=True) if equal_times else list(reversed(ids))
    page = client.get("/orders", params={"sort": "newest", "limit": 1}).json()
    cursor = page["next_cursor"]
    seen = [page["items"][0]["order_id"]]
    while page["next_cursor"]:
        page = client.get("/orders", params={
            "sort": "newest", "limit": 1, "cursor": page["next_cursor"],
        }).json()
        seen.extend(row["order_id"] for row in page["items"])
    assert seen == expected
    assert client.get("/orders").json()["items"][0]["order_id"] == expected[-1]
    assert client.get("/orders", params={"limit": 1, "cursor": cursor}).status_code == 422
    oldest_cursor = client.get("/orders", params={"limit": 1}).json()["next_cursor"]
    assert client.get("/orders", params={
        "sort": "newest", "limit": 1, "cursor": oldest_cursor,
    }).status_code == 422
    assert client.get("/orders", params={"sort": "invalid"}).status_code == 422


def test_cursor_scope_pagination_filters_and_tampering(api):
    client, state, _ = api
    for _ in range(3):
        rx = uuid4()
        assert create(client, key=str(rx), rx=rx).status_code == 201
    page = client.get("/orders", params={"limit": 1}).json()
    seen = [page["items"][0]["order_id"]]
    cursor = page["next_cursor"]
    while page["next_cursor"]:
        page = client.get("/orders", params={"limit": 1, "cursor": page["next_cursor"]}).json()
        seen += [row["order_id"] for row in page["items"]]
    assert len(seen) == len(set(seen)) == 3
    assert client.get("/orders", params={"cursor": cursor, "limit": 2}).status_code == 422
    assert (
        client.get("/orders", params={"cursor": cursor + "broken", "limit": 1}).status_code == 422
    )
    assert client.get("/orders", params={"status": "paid"}).json()["items"] == []
    assert client.get("/orders", params={"tenant_id": str(OTHER_TENANT)}).json()["items"] == []
    state.identity = identity(subject=OTHER_PATIENT)
    assert client.get("/orders", params={"cursor": cursor, "limit": 1}).status_code == 422
    state.identity = identity(roles=(), clinic_role="clinic_admin")
    path = f"/clinics/{TENANT}/catalogue"
    for _ in range(3):
        assert client.put(f"{path}/{uuid4()}", json=catalogue_body()).status_code == 201
    page = client.get(path, params={"limit": 2}).json()
    second = client.get(path, params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert len(page["items"]) == len(second["items"]) == 2
    assert second["next_cursor"] is None
    state.identity = identity(roles=(), clinic_role="doctor")
    assert client.get(path, params={"limit": 2, "cursor": page["next_cursor"]}).status_code == 422
