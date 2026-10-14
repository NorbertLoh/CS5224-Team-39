import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telelink_common.access import IdentityClient

from app.database import create_database_engine
from app.main import create_app
from app.models import Appointment, AvailabilitySlot
from app.settings import Settings
from app.tenant import TenantClient

CURSOR = "s02-cursor-test-secret-at-least-32-bytes"
SERVICE = "s02-booking-test-secret-at-least-32-bytes"


def configuration(**changes):
    return Settings(
        _env_file=None,
        **{
            "environment": "test",
            "auth_issuer": "http://localhost/test-pool",
            "auth_jwks_url": "http://localhost/test-pool/jwks",
            "auth_client_id": "test-web",
            "identity_url": "http://identity.test",
            "tenant_url": "http://tenant.test",
            "cursor_secret": CURSOR,
            "scheduling_secret": SERVICE,
        }
        | changes,
    )


@pytest.fixture(scope="module")
def api_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL API tests")
    if os.environ.get("SCHEDULING_TEST_ALLOW_RESET") != "1":
        pytest.fail("Use a disposable database and SCHEDULING_TEST_ALLOW_RESET=1")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    try:
        yield engine, url
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


@pytest.fixture
def api(api_database):
    engine, url = api_database
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ids = {name: uuid4() for name in ("doctor", "other_doctor", "patient", "admin", "platform")}
    tenant_a, tenant_b = uuid4(), uuid4()
    memberships = {}
    for name in ids:
        role = "doctor" if "doctor" in name else "clinic_admin"
        memberships[name] = (
            []
            if name in {"patient", "platform"}
            else [
                {
                    "membership_id": str(uuid4()),
                    "subject_id": str(ids[name]),
                    "tenant_id": str(tenant_a),
                    "roles": [role],
                    "status": "active",
                    "created_at": "2026-10-14T00:00:00Z",
                    "updated_at": "2026-10-14T00:00:00Z",
                }
            ]
        )
    state = {
        "active": True,
        "price": 2500,
        "tenant_error": None,
        "doctor_error": None,
        "identity_error": None,
        "directory": [ids["doctor"], ids["other_doctor"]],
    }
    settings = configuration(database_url=url)
    app = create_app(settings)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def identity_http(request):
        assert request.url.path == "/me"
        if state["identity_error"]:
            return httpx.Response(state["identity_error"])
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            key.public_key(),
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
        )
        name = claims["sub"]
        return httpx.Response(
            200,
            json={
                "subject_id": str(ids[name]),
                "cognito_sub": name,
                "display_name": name,
                "global_roles": ["platform_admin"] if name == "platform" else ["patient"],
                "memberships": memberships[name],
            },
        )

    def tenant_http(request):
        if "/booking-profile" in request.url.path:
            claims = jwt.decode(
                request.headers["Authorization"].split()[1],
                SERVICE,
                algorithms=["HS256"],
                issuer="telelink-service:scheduling",
                audience="telelink-tenant-booking",
            )
            assert claims["sub"] == "scheduling" and claims["exp"] - claims["iat"] == 60
            if state["tenant_error"]:
                return httpx.Response(state["tenant_error"])
            if not state["active"]:
                return httpx.Response(409)
            tenant_id = request.url.path.split("/")[3]
            return httpx.Response(
                200,
                json={
                    "tenant_id": tenant_id,
                    "status": "active",
                    "consultation_price": {"amount_minor": state["price"], "currency": "SGD"},
                },
            )
        assert request.url.path.endswith("/doctors")
        if state["doctor_error"]:
            return httpx.Response(state["doctor_error"])
        return httpx.Response(
            200,
            json={
                "items": [
                    {"doctor_id": str(doctor), "display_name": "Doctor"}
                    for doctor in state["directory"]
                ],
                "next_cursor": None,
            },
        )

    def user(name="doctor", **changes):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": settings.auth_issuer,
                "sub": name,
                "iat": now,
                "exp": now + 300,
                "token_use": "access",
                "client_id": "test-web",
            }
            | changes,
            key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )
        return {"Authorization": "Bearer " + token}

    with TestClient(app) as client:
        app.state.identity_client.close()
        app.state.tenant_client.close()
        app.state.identity_client = IdentityClient(
            settings, transport=httpx.MockTransport(identity_http)
        )
        app.state.tenant_client = TenantClient(settings, transport=httpx.MockTransport(tenant_http))
        yield client, user, tenant_a, tenant_b, ids, state, memberships, engine


def slot_body(start=None):
    start = start or datetime.now(timezone.utc) + timedelta(days=1)
    return {"starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=30)).isoformat()}


def list_params(body):
    return {
        "from": body["starts_at"],
        "to": (datetime.fromisoformat(body["starts_at"]) + timedelta(days=1)).isoformat(),
    }


def test_create_list_delete_and_trusted_price(api):
    client, user, tenant, _, ids, state, _, engine = api
    body = slot_body()
    created = client.post(f"/clinics/{tenant}/slots", json=body, headers=user())
    assert created.status_code == 201, created.text
    slot = created.json()
    assert slot["doctor_id"] == str(ids["doctor"])
    assert slot["availability"] == "available"
    assert slot["consultation_price"] == {"amount_minor": 2500, "currency": "SGD"}
    state["price"] = 3000
    listed = client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()
    assert listed["items"][0]["consultation_price"]["amount_minor"] == 3000
    assert "patient_id" not in listed["items"][0] and "payment_id" not in listed["items"][0]
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 204
    assert client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()["items"] == []
    with Session(engine) as session:
        stored = session.scalar(
            select(AvailabilitySlot).where(AvailabilitySlot.slot_id == slot["slot_id"])
        )
        assert stored.withdrawn_at is not None
    assert client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).status_code == 201


@pytest.mark.parametrize("name", ["patient", "admin", "platform"])
def test_only_member_doctors_create(api, name):
    client, user, tenant, _, *_ = api
    assert (
        client.post(f"/clinics/{tenant}/slots", json=slot_body(), headers=user(name)).status_code
        == 404
    )


def test_revoked_membership_and_cross_tenant(api):
    client, user, tenant, other_tenant, _, _, memberships, _ = api
    assert (
        client.post(f"/clinics/{other_tenant}/slots", json=slot_body(), headers=user()).status_code
        == 404
    )
    memberships["doctor"][0]["status"] = "revoked"
    assert (
        client.post(f"/clinics/{tenant}/slots", json=slot_body(), headers=user()).status_code == 404
    )


@pytest.mark.parametrize("changes", [{"token_use": "id"}, {"exp": 1}, {"client_id": "other"}])
def test_invalid_access_tokens(api, changes):
    client, user, tenant, _, *_ = api
    assert (
        client.post(
            f"/clinics/{tenant}/slots", json=slot_body(), headers=user(**changes)
        ).status_code
        == 401
    )


def test_no_header_bypass(api):
    client, _, tenant, _, ids, *_ = api
    response = client.post(
        f"/clinics/{tenant}/slots",
        json=slot_body(),
        headers={
            "X-Subject-ID": str(ids["doctor"]),
            "X-Tenant-ID": str(tenant),
            "X-Role": "doctor",
        },
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"doctor_id": str(uuid4())},
        {"consultation_price": {"amount_minor": 1, "currency": "SGD"}},
        {"starts_at": "2026-10-14T00:00:00"},
        {"starts_at": 123456},
        {"starts_at": "123456"},
        {"ends_at": "2030-01-01T00:00:00Z"},
    ],
)
def test_invalid_slot_input(api, change):
    client, user, tenant, _, *_ = api
    assert (
        client.post(
            f"/clinics/{tenant}/slots", json=slot_body() | change, headers=user()
        ).status_code
        == 422
    )


def test_past_slot_and_inactive_clinic(api):
    client, user, tenant, _, _, state, *_ = api
    assert (
        client.post(
            f"/clinics/{tenant}/slots",
            json=slot_body(datetime.now(timezone.utc) - timedelta(hours=1)),
            headers=user(),
        ).status_code
        == 422
    )
    state["active"] = False
    assert (
        client.post(f"/clinics/{tenant}/slots", json=slot_body(), headers=user()).status_code == 409
    )
    assert (
        client.get(f"/clinics/{tenant}/slots", params=list_params(slot_body())).status_code == 404
    )


def test_overlap_across_clinics_and_concurrent_create(api):
    client, user, tenant, other, ids, _, memberships, _ = api
    memberships["doctor"].append(
        memberships["doctor"][0] | {"membership_id": str(uuid4()), "tenant_id": str(other)}
    )
    body, headers = slot_body(), user()

    def create(_):
        return client.post(f"/clinics/{tenant}/slots", json=body, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(create, range(2))) == [201, 409]
    assert client.post(f"/clinics/{other}/slots", json=body, headers=headers).status_code == 409
    assert (
        client.post(f"/clinics/{tenant}/slots", json=body, headers=user("other_doctor")).status_code
        == 201
    )


@pytest.mark.parametrize("status", ["held", "pending_payment", "confirmed", "in_progress"])
def test_reserved_slot_blocks_delete_and_hides_participants(api, status):
    client, user, tenant, _, ids, _, _, engine = api
    body = slot_body()
    slot = client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).json()
    with Session(engine) as session, session.begin():
        session.add(
            Appointment(
                slot_id=slot["slot_id"],
                tenant_id=tenant,
                doctor_id=ids["doctor"],
                patient_id=ids["patient"],
                starts_at=datetime.fromisoformat(body["starts_at"]),
                ends_at=datetime.fromisoformat(body["ends_at"]),
                status=status,
                hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=9)
                if status in {"held", "pending_payment"}
                else None,
                consultation_price_minor=2500,
            )
        )
    listed = client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()["items"][0]
    assert listed["availability"] == "unavailable" and "patient_id" not in listed
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 409
    assert (
        client.delete("/slots/" + slot["slot_id"], headers=user("other_doctor")).status_code == 404
    )


def test_ineligible_doctors_filtered_and_permissions_rechecked(api):
    client, user, tenant, _, _, state, memberships, _ = api
    body = slot_body()
    slot = client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).json()
    state["directory"] = []
    assert client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()["items"] == []
    memberships["doctor"] = []
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 404


@pytest.mark.parametrize("status", ["cancelled", "expired", "completed", "no_show"])
def test_withdrawal_preserves_appointment_history(api, status):
    client, user, tenant, _, ids, _, _, engine = api
    body = slot_body()
    slot = client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).json()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        appointment = Appointment(
            slot_id=slot["slot_id"],
            tenant_id=tenant,
            doctor_id=ids["doctor"],
            patient_id=ids["patient"],
            status=status,
            starts_at=datetime.fromisoformat(body["starts_at"]),
            ends_at=datetime.fromisoformat(body["ends_at"]),
            consultation_price_minor=2500,
            hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=9)
            if status in {"cancelled", "expired"}
            else None,
        )
        session.add(appointment)
        session.flush()
        appointment_id = appointment.appointment_id
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 204
    with Session(engine) as session:
        assert session.get(Appointment, appointment_id).slot_id == UUID(slot["slot_id"])


def test_rollback_refuses_to_destroy_replaced_slot_history(api):
    client, user, tenant, _, *_ = api
    body = slot_body()
    slot = client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).json()
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 204
    assert client.post(f"/clinics/{tenant}/slots", json=body, headers=user()).status_code == 201
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(IntegrityError):
        command.downgrade(config, "0001")
    engine = api[-1]
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM scheduling.alembic_version")) == "0002"
        )


def test_cursor_pagination_filter_binding_and_tampering(api):
    client, user, tenant, other, ids, *_ = api
    body = slot_body()
    for offset in range(3):
        client.post(
            f"/clinics/{tenant}/slots",
            json=slot_body(datetime.fromisoformat(body["starts_at"]) + timedelta(hours=offset)),
            headers=user(),
        ).raise_for_status()
    path, params = f"/clinics/{tenant}/slots", list_params(body) | {"limit": 1}
    page = client.get(path, params=params).json()
    cursor = page["next_cursor"]
    page2 = client.get(path, params=params | {"cursor": cursor}).json()
    assert page["items"][0]["slot_id"] != page2["items"][0]["slot_id"]
    assert (
        client.get(
            path, params=params | {"cursor": cursor, "doctor_id": str(ids["doctor"])}
        ).status_code
        == 422
    )
    assert (
        client.get(f"/clinics/{other}/slots", params=params | {"cursor": cursor}).status_code == 422
    )
    assert client.get(path, params=params | {"cursor": cursor + "x"}).status_code == 422
    assert client.get(path, params=params | {"cursor": ""}).status_code == 422
    assert client.get(path, params=params | {"doctor_id": str(uuid4())}).json()["items"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"from": "2026-10-14T00:00:00"},
        {"from": "1234"},
        {"limit": 0},
        {"limit": 101},
        {"to": "2000-01-01T00:00:00Z"},
        {"to": "2030-01-01T00:00:00Z"},
    ],
)
def test_list_validation(api, change):
    client, _, tenant, *_ = api
    assert (
        client.get(f"/clinics/{tenant}/slots", params=list_params(slot_body()) | change).status_code
        == 422
    )


@pytest.mark.parametrize("upstream", ["tenant_error", "doctor_error", "identity_error"])
def test_upstream_failures_closed(api, upstream):
    client, user, tenant, _, _, state, *_ = api
    state[upstream] = 503
    if upstream == "identity_error":
        response = client.post(f"/clinics/{tenant}/slots", json=slot_body(), headers=user())
    else:
        response = client.get(f"/clinics/{tenant}/slots", params=list_params(slot_body()))
    assert response.status_code == 503
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "changes",
    [
        {
            "tenant_url": "http://example.com",
            "environment": "production",
            "auth_issuer": None,
            "auth_jwks_url": None,
            "auth_client_id": None,
        },
        {"tenant_url": "http://user:pass@localhost"},
        {"cursor_secret": "short"},
        {"cursor_secret": SERVICE},
        {"cors_origins": ["*"]},
    ],
)
def test_configuration_guards(changes):
    with pytest.raises(ValidationError):
        configuration(**changes)


def test_missing_configuration_health_and_cors():
    app = create_app(
        Settings(_env_file=None, environment="test", cors_origins=["http://localhost:5173"])
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        response = client.options(
            "/slots/" + str(uuid4()),
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
