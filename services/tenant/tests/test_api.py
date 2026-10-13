import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from telelink_common.access import IdentityClient

from app.database import create_database_engine
from app.main import create_app
from app.models import Clinic
from app.settings import Settings

CURSOR = "cursor-secret-for-tests-at-least-32-bytes"
TENANT = "tenant-secret-for-tests-at-least-32-bytes"
BOOKING = "booking-secret-for-tests-at-least-32-bytes"


def configuration(**changes):
    return Settings(
        _env_file=None,
        **{
            "environment": "test",
            "auth_issuer": "http://localhost/test-pool",
            "auth_jwks_url": "http://localhost/test-pool/jwks",
            "auth_client_id": "test-web",
            "identity_url": "http://identity.test",
            "cursor_secret": CURSOR,
            "tenant_secret": TENANT,
            "scheduling_secret": BOOKING,
        }
        | changes,
    )


def body(**changes):
    return {
        "slug": f"demo-{uuid4()}",
        "name": "Synthetic clinic",
        "branding": {"primary_color": "#156B63", "logo_url": None, "description": "Demo"},
        "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
    } | changes


@pytest.fixture(scope="module")
def api_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for tenant API checks")
    if os.environ.get("TENANT_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set TENANT_TEST_ALLOW_RESET=1 for disposable PostgreSQL")
    old = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    try:
        yield engine, url
    finally:
        engine.dispose()
        if old is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old


@pytest.fixture
def api(api_database):
    engine, url = api_database
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ids = {name: uuid4() for name in ("creator", "other", "platform", "doctor")}
    memberships = {name: [] for name in ids}
    state = {"fail": False, "mismatch": False, "calls": 0}
    settings = configuration(database_url=url)
    app = create_app(settings)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def identity_http(request):
        if request.url.path == "/me":
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
        assert request.url.path == "/internal/clinic-creators"
        state["calls"] += 1
        jwt.decode(
            request.headers["Authorization"].split()[1],
            TENANT,
            algorithms=["HS256"],
            issuer="telelink-service:tenant",
            audience="telelink-identity-provisioning",
        )
        data = json.loads(request.content)
        membership = {
            "membership_id": str(uuid4()),
            "subject_id": data["subject_id"],
            "tenant_id": data["tenant_id"],
            "roles": ["clinic_admin"],
            "status": "active",
            "created_at": "2026-10-13T00:00:00Z",
            "updated_at": "2026-10-13T00:00:00Z",
        }
        # Simulate identity commit followed by a lost acknowledgement.
        if not memberships["creator"]:
            memberships["creator"].append(membership)
        if state["fail"]:
            raise httpx.ReadTimeout("Synthetic lost acknowledgement", request=request)
        if state["mismatch"]:
            membership["subject_id"] = str(uuid4())
        return httpx.Response(200, json=membership)

    def user(name="creator", **changes):
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": name,
                "iss": settings.auth_issuer,
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

    def booking(**changes):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": "telelink-service:scheduling",
                "aud": "telelink-tenant-booking",
                "sub": "scheduling",
                "iat": now,
                "exp": now + 60,
            }
            | changes,
            BOOKING,
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}

    with TestClient(app) as client:
        app.state.identity_client.close()
        app.state.identity_client = IdentityClient(
            settings, transport=httpx.MockTransport(identity_http)
        )
        yield SimpleNamespace(
            client=client,
            user=user,
            booking=booking,
            engine=engine,
            state=state,
            memberships=memberships,
            app=app,
        )


def activate(api, tenant_id, **changes):
    with Session(api.engine) as session, session.begin():
        clinic = session.get(Clinic, tenant_id)
        clinic.status = "active"
        for key, value in changes.items():
            setattr(clinic, key, value)


def test_creation_admin_update_and_public_profile(api):
    payload = body()
    response = api.client.post("/clinics", json=payload, headers=api.user())
    assert response.status_code == 201
    created = response.json()
    tenant_id = created["tenant_id"]
    assert created["status"] == "pending_review" and created["commission_bps"] == 0
    assert api.client.get(f"/clinics/by-slug/{payload['slug']}").status_code == 404
    assert api.client.get(f"/clinics/{tenant_id}", headers=api.user()).status_code == 200
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 200
    assert api.state["calls"] == 1
    assert (
        api.client.post("/clinics", json=payload, headers=api.user("other")).json()["error"]["code"]
        == "slug_taken"
    )
    assert api.client.get(f"/clinics/{tenant_id}", headers=api.user("other")).status_code == 404
    assert (
        api.client.patch(
            f"/clinics/{tenant_id}", json={"name": "Updated"}, headers=api.user("other")
        ).status_code
        == 404
    )
    updated = api.client.patch(
        f"/clinics/{tenant_id}", json={"name": "Updated"}, headers=api.user()
    )
    assert updated.status_code == 200 and updated.json()["name"] == "Updated"
    assert api.client.get(f"/clinics/{tenant_id}", headers=api.user("platform")).status_code == 200
    activate(api, tenant_id)
    public = api.client.get(f"/clinics/by-slug/{payload['slug']}").json()
    assert public["name"] == "Updated"
    assert (
        not {"commission_bps", "review_reason", "creator_subject_id", "membership_provisioned"}
        & public.keys()
    )
    assert public["created_at"].endswith("Z")


def test_recovery_from_lost_identity_acknowledgement(api):
    payload = body()
    api.state["fail"] = True
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 503
    with Session(api.engine) as session:
        clinic = session.scalar(select(Clinic).where(Clinic.slug == payload["slug"]))
        tenant_id = clinic.tenant_id
        assert not clinic.membership_provisioned
    activate(api, tenant_id)
    path = f"/internal/clinics/{tenant_id}/booking-profile"
    assert api.client.get(path, headers=api.booking()).status_code == 409
    assert api.client.get(f"/clinics/by-slug/{payload['slug']}").status_code == 404
    api.state["fail"] = False
    result = api.client.post("/clinics", json=payload, headers=api.user())
    assert result.status_code == 200 and result.json()["tenant_id"] == str(tenant_id)
    assert api.client.get(path, headers=api.booking()).status_code == 200
    assert len(api.memberships["creator"]) == 1


@pytest.mark.parametrize("status", ["pending_review", "rejected", "suspended"])
def test_inactive_booking_gate(api, status):
    created = api.client.post("/clinics", json=body(), headers=api.user()).json()
    tenant_id = created["tenant_id"]
    activate(api, tenant_id, status=status)
    result = api.client.get(f"/internal/clinics/{tenant_id}/booking-profile", headers=api.booking())
    assert result.status_code == 409 and result.json()["error"]["code"] == "clinic_not_active"
    assert api.client.get(f"/clinics/by-slug/{created['slug']}").status_code == 404


def test_authentication_and_booking_service_scope(api):
    assert api.client.post("/clinics", json=body()).status_code == 401
    assert (
        api.client.post("/clinics", json=body(), headers=api.user(token_use="id")).status_code
        == 401
    )
    assert (
        api.client.get(f"/clinics/{uuid4()}", headers={"X-Subject-ID": "creator"}).status_code
        == 401
    )
    path = f"/internal/clinics/{uuid4()}/booking-profile"
    assert api.client.get(path).status_code == 401
    assert api.client.get(path, headers=api.user()).status_code == 401
    assert (
        api.client.get(path, headers=api.booking(aud="telelink-identity-access")).status_code == 401
    )
    assert api.client.get(path, headers=api.booking(exp=int(time.time()) - 1)).status_code == 401
    assert api.client.get(path, headers=api.booking()).status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"name": None},
        {"name": "  "},
        {"slug": "changed"},
        {"status": "active"},
        {"commission_bps": 1000},
        {"branding": {"primary_color": "#abcdef"}},
    ],
)
def test_update_validation(api, patch):
    created = api.client.post("/clinics", json=body(), headers=api.user()).json()
    result = api.client.patch(f"/clinics/{created['tenant_id']}", json=patch, headers=api.user())
    assert result.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "active"},
        {"commission_bps": 1000},
        {"name": " "},
        {"slug": "Bad Slug"},
        {"consultation_price": {"amount_minor": True, "currency": "SGD"}},
        {"consultation_price": {"amount_minor": -1, "currency": "SGD"}},
        {"consultation_price": {"amount_minor": 1, "currency": "USD"}},
        {"branding": {"primary_color": "red", "logo_url": None, "description": "Demo"}},
        {
            "branding": {
                "primary_color": "#123456",
                "logo_url": "http://example.com",
                "description": "Demo",
            }
        },
        {
            "branding": {
                "primary_color": "#123456",
                "logo_url": None,
                "description": "<script>x</script>",
            }
        },
    ],
)
def test_create_validation(api, changes):
    assert api.client.post("/clinics", json=body(**changes), headers=api.user()).status_code == 422


def test_pagination_and_unprovisioned_filter(api):
    for _ in range(3):
        created = api.client.post(
            "/clinics", json=body(name="Same name"), headers=api.user()
        ).json()
        activate(api, created["tenant_id"])
    first = api.client.get("/clinics?limit=1").json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = api.client.get("/clinics", params={"limit": 1, "cursor": first["next_cursor"]}).json()
    assert second["items"][0]["tenant_id"] != first["items"][0]["tenant_id"]
    assert api.client.get("/clinics?cursor=bad").status_code == 422
    assert api.client.get("/clinics?limit=101").status_code == 422


def test_invalid_provisioning_acknowledgement(api):
    api.state["mismatch"] = True
    payload = body()
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 503
    with Session(api.engine) as session:
        clinic = session.scalar(select(Clinic).where(Clinic.slug == payload["slug"]))
        assert not clinic.membership_provisioned


def test_revoked_creator_cannot_use_creation_retry_for_admin_access(api):
    payload = body()
    result = api.client.post("/clinics", json=payload, headers=api.user())
    assert result.status_code == 201
    api.memberships["creator"].clear()
    assert api.client.post("/clinics", json=payload, headers=api.user()).status_code == 404
    assert api.state["calls"] == 1


def test_health_and_unconfigured_authentication():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.post("/clinics", json=body()).status_code == 401
