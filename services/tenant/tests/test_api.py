import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telelink_common.access import IdentityClient

from app import admin
from app.database import create_database_engine
from app.logos import MAX_LOGO_BYTES, LogoStorage, logo_png
from app.main import create_app
from app.models import AuditEvent, Clinic
from app.settings import Settings

CURSOR = "cursor-secret-for-tests-at-least-32-bytes"
TENANT = "tenant-secret-for-tests-at-least-32-bytes"
BOOKING = "booking-secret-for-tests-at-least-32-bytes"
IDENTITY = "identity-secret-for-tests-at-least-32-bytes"


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
            "identity_secret": IDENTITY,
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
            ids=ids,
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


def audit_events(api, tenant_id):
    with Session(api.engine) as session:
        return session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.event_id)
        ).all()


def create_for_review(api, status="pending_review"):
    clinic = api.client.post("/clinics", json=body(), headers=api.user()).json()
    if status != "pending_review":
        activate(api, clinic["tenant_id"], status=status)
    return clinic["tenant_id"]


@pytest.mark.parametrize(
    "initial,decision,target",
    [
        ("pending_review", "approve", "active"),
        ("pending_review", "reject", "rejected"),
        ("pending_review", "suspend", None),
        ("active", "approve", "active"),
        ("active", "reject", None),
        ("active", "suspend", "suspended"),
        ("rejected", "approve", "active"),
        ("rejected", "reject", "rejected"),
        ("rejected", "suspend", None),
        ("suspended", "approve", "active"),
        ("suspended", "reject", None),
        ("suspended", "suspend", "suspended"),
    ],
)
def test_review_transition_contract(api, initial, decision, target):
    tenant_id = create_for_review(api, initial)
    payload = {
        "decision": decision,
        "reason": None if decision == "approve" else "Synthetic reason",
    }
    response = api.client.post(
        f"/clinics/{tenant_id}/review", json=payload, headers=api.user("platform")
    )
    events = audit_events(api, tenant_id)
    if target is None:
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_clinic_transition"
        assert not events
    else:
        assert response.status_code == 200 and response.json()["status"] == target
        assert len(events) == (0 if initial == target else 1)
        if events:
            event = events[0]
            assert event.actor_subject_id == api.ids["platform"]
            assert event.previous_values["status"] == initial
            assert event.new_values == {"status": target, "review_reason": payload["reason"]}
            assert event.reason == payload["reason"]
            assert event.occurred_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "reject"},
        {"decision": "suspend", "reason": "  "},
        {"decision": "approve", "reason": "Not allowed"},
        {"decision": "unknown"},
        {"decision": "reject", "reason": "<b>HTML</b>"},
        {"decision": "approve", "actor_subject_id": str(uuid4())},
    ],
)
def test_review_input_validation(api, payload):
    tenant_id = create_for_review(api)
    assert (
        api.client.post(
            f"/clinics/{tenant_id}/review", json=payload, headers=api.user("platform")
        ).status_code
        == 422
    )
    assert not audit_events(api, tenant_id)


@pytest.mark.parametrize("role", ["creator", "other", "doctor"])
def test_platform_routes_reject_other_roles(api, role):
    tenant_id = create_for_review(api)
    credential = api.user(role)
    assert api.client.get("/admin/clinics", headers=credential).status_code == 403
    assert (
        api.client.post(
            f"/clinics/{tenant_id}/review", json={"decision": "approve"}, headers=credential
        ).status_code
        == 403
    )
    assert (
        api.client.put(
            f"/clinics/{tenant_id}/commission", json={"commission_bps": 1000}, headers=credential
        ).status_code
        == 403
    )
    assert not audit_events(api, tenant_id)


@pytest.mark.parametrize("value", [-1, 10001, True, 100.5, "1000", None])
def test_commission_validation(api, value):
    tenant_id = create_for_review(api)
    assert (
        api.client.put(
            f"/clinics/{tenant_id}/commission",
            json={"commission_bps": value},
            headers=api.user("platform"),
        ).status_code
        == 422
    )
    assert not audit_events(api, tenant_id)


def test_commission_changes_are_audited_and_retries_are_noops(api):
    tenant_id = create_for_review(api)
    path = f"/clinics/{tenant_id}/commission"
    for value in (1000, 10000, 0):
        response = api.client.put(
            path, json={"commission_bps": value}, headers=api.user("platform")
        )
        assert response.status_code == 200 and response.json()["commission_bps"] == value
        repeated = api.client.put(
            path, json={"commission_bps": value}, headers=api.user("platform")
        )
        assert repeated.json()["updated_at"] == response.json()["updated_at"]
    events = audit_events(api, tenant_id)
    assert [(item.previous_values, item.new_values) for item in events] == [
        ({"commission_bps": 0}, {"commission_bps": 1000}),
        ({"commission_bps": 1000}, {"commission_bps": 10000}),
        ({"commission_bps": 10000}, {"commission_bps": 0}),
    ]
    assert all(
        item.action == "clinic.commission_changed" and item.reason is None for item in events
    )


@pytest.mark.parametrize("operation", ["review", "commission"])
def test_concurrent_identical_admin_requests_emit_one_event(api, operation):
    tenant_id = create_for_review(api)
    credential = api.user("platform")

    def change(_):
        if operation == "review":
            return api.client.post(
                f"/clinics/{tenant_id}/review", json={"decision": "approve"}, headers=credential
            )
        return api.client.put(
            f"/clinics/{tenant_id}/commission", json={"commission_bps": 1000}, headers=credential
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(change, range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert len(audit_events(api, tenant_id)) == 1


@pytest.mark.parametrize("operation", ["review", "commission"])
def test_audit_insert_failure_rolls_back_clinic_change(api, monkeypatch, operation):
    tenant_id = create_for_review(api)

    def invalid_audit(session, clinic, *args):
        session.add(
            AuditEvent(
                tenant_id=clinic.tenant_id,
                actor_subject_id=None,
                action="clinic.approved",
                previous_values={},
                new_values={},
            )
        )

    monkeypatch.setattr(admin, "record_audit", invalid_audit)
    if operation == "review":
        result = api.client.post(
            f"/clinics/{tenant_id}/review",
            json={"decision": "approve"},
            headers=api.user("platform"),
        )
    else:
        result = api.client.put(
            f"/clinics/{tenant_id}/commission",
            json={"commission_bps": 1000},
            headers=api.user("platform"),
        )
    assert result.status_code == 409
    with Session(api.engine) as session:
        clinic = session.get(Clinic, tenant_id)
        assert clinic.status == "pending_review" and clinic.commission_bps == 0
    assert not audit_events(api, tenant_id)


def test_approval_and_suspension_control_public_and_booking_access(api):
    tenant_id = create_for_review(api)
    with Session(api.engine) as session:
        slug = session.get(Clinic, tenant_id).slug
    review_path = f"/clinics/{tenant_id}/review"
    gate = f"/internal/clinics/{tenant_id}/booking-profile"
    public = f"/clinics/by-slug/{slug}"
    for decision, expected in [("approve", 200), ("suspend", 409), ("approve", 200)]:
        payload = {
            "decision": decision,
            "reason": "Synthetic suspension" if decision == "suspend" else None,
        }
        response = api.client.post(review_path, json=payload, headers=api.user("platform"))
        assert response.status_code == 200
        assert api.client.get(gate, headers=api.booking()).status_code == expected
        assert api.client.get(public).status_code == (200 if expected == 200 else 404)
    assert api.client.get(public).json()["status"] == "active"
    assert len(audit_events(api, tenant_id)) == 3


def test_audit_records_are_append_only(api):
    tenant_id = create_for_review(api)
    api.client.post(
        f"/clinics/{tenant_id}/review", json={"decision": "approve"}, headers=api.user("platform")
    ).raise_for_status()
    for sql in (
        "UPDATE tenant.audit_events SET reason='changed' WHERE tenant_id=:id",
        "DELETE FROM tenant.audit_events WHERE tenant_id=:id",
    ):
        with pytest.raises(IntegrityError) as error, api.engine.begin() as connection:
            connection.execute(text(sql), {"id": tenant_id})
        assert error.value.orig.sqlstate == "23514"
    assert len(audit_events(api, tenant_id)) == 1


def test_approval_cannot_bypass_missing_creator_provisioning(api):
    tenant_id = create_for_review(api)
    with Session(api.engine) as session, session.begin():
        clinic = session.get(Clinic, tenant_id)
        clinic.membership_provisioned = False
        slug = clinic.slug
    result = api.client.post(
        f"/clinics/{tenant_id}/review", json={"decision": "approve"}, headers=api.user("platform")
    )
    assert result.status_code == 200
    assert api.client.get(f"/clinics/by-slug/{slug}").status_code == 404
    assert (
        api.client.get(
            f"/internal/clinics/{tenant_id}/booking-profile", headers=api.booking()
        ).status_code
        == 409
    )


def test_admin_list_filter_pagination_and_unknown_clinics(api):
    create_for_review(api)
    credential = api.user("platform")
    first = api.client.get(
        "/admin/clinics", params={"status": "pending_review", "limit": 1}, headers=credential
    ).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    assert "commission_bps" in first["items"][0]
    second = api.client.get(
        "/admin/clinics",
        params={"status": "pending_review", "limit": 1, "cursor": first["next_cursor"]},
        headers=credential,
    ).json()
    assert first["items"][0]["tenant_id"] != second["items"][0]["tenant_id"]
    assert (
        api.client.get(
            "/admin/clinics",
            params={"status": "active", "cursor": first["next_cursor"]},
            headers=credential,
        ).status_code
        == 422
    )
    assert api.client.get("/admin/clinics?cursor=bad", headers=credential).status_code == 422
    assert api.client.get("/admin/clinics?status=invalid", headers=credential).status_code == 422
    assert api.client.get("/admin/clinics").status_code == 401
    assert (
        api.client.post(
            f"/clinics/{uuid4()}/review", json={"decision": "approve"}, headers=credential
        ).status_code
        == 404
    )
    assert (
        api.client.put(
            f"/clinics/{uuid4()}/commission", json={"commission_bps": 1000}, headers=credential
        ).status_code
        == 404
    )


def identity_service_token(**changes):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-service:identity",
            "aud": "telelink-tenant-memberships",
            "sub": "identity",
            "iat": now,
            "exp": now + 60,
        }
        | changes,
        IDENTITY,
        algorithm="HS256",
    )


@pytest.mark.parametrize("status", ["pending_review", "active", "rejected", "suspended"])
def test_membership_profile_allows_staff_admin_in_all_clinic_states(api, status):
    created = api.client.post("/clinics", json=body(), headers=api.user()).json()
    tenant_id = created["tenant_id"]
    with Session(api.engine) as session, session.begin():
        session.get(Clinic, tenant_id).status = status
    auth = {"Authorization": "Bearer " + identity_service_token()}
    response = api.client.get(f"/internal/clinics/{tenant_id}/membership-profile", headers=auth)
    assert response.status_code == 200
    assert response.json() == {"tenant_id": tenant_id}
    assert (
        api.client.get(f"/internal/clinics/{uuid4()}/membership-profile", headers=auth).status_code
        == 404
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "telelink-service:tenant"},
        {"aud": "telelink-tenant-booking"},
        {"sub": "scheduling"},
        {"exp": 1},
        {"exp": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600},
        {"iat": "invalid"},
    ],
)
def test_membership_profile_rejects_invalid_service_claims(api, changes):
    response = api.client.get(
        f"/internal/clinics/{uuid4()}/membership-profile",
        headers={"Authorization": "Bearer " + identity_service_token(**changes)},
    )
    assert response.status_code == 401


def test_membership_profile_rejects_user_and_other_service_tokens(api):
    endpoint = f"/internal/clinics/{uuid4()}/membership-profile"
    for auth in ({}, api.user(), api.booking(), {"Authorization": "Bearer invalid"}):
        assert api.client.get(endpoint, headers=auth).status_code == 401
    api.app.state.settings.identity_secret = None
    assert (
        api.client.get(
            endpoint, headers={"Authorization": "Bearer " + identity_service_token()}
        ).status_code
        == 503
    )


def logo_bytes(color="red", image_format="PNG", size=(20, 20)):
    output = BytesIO()
    Image.new("RGB", size, color).save(output, image_format)
    return output.getvalue()


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.versioning = {}
        self.fail = False

    def get_bucket_versioning(self, **kwargs):
        if self.fail:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "GetBucketVersioning")
        return self.versioning

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def close(self):
        pass


def configure_logo_storage(api):
    settings = configuration(
        logo_bucket="test-logos", logo_public_base_url="https://assets.example"
    )
    storage = LogoStorage(configuration())
    storage.settings = settings
    storage.client = MemoryS3()
    api.app.state.logo_storage = storage
    api.app.state.settings.logo_bucket = "test-logos"
    return storage


def test_logo_upload_replace_remove_and_permissions(api):
    tenant = api.client.post("/clinics", json=body(), headers=api.user()).json()["tenant_id"]
    storage = configure_logo_storage(api)
    endpoint = f"/clinics/{tenant}/logo"
    for name in ("other", "doctor"):
        for method in ("put", "delete", "get"):
            assert (
                api.client.request(
                    method, endpoint, headers=api.user(name), content=logo_bytes()
                ).status_code
                == 404
            )
    assert not storage.client.objects
    for color in ("red", "blue"):
        response = api.client.put(endpoint, content=logo_bytes(color), headers=api.user())
        assert response.status_code == 200
        assert (
            response.json()["branding"]["logo_url"]
            == f"https://assets.example/clinic-logos/{tenant}/logo.png"
        )
        assert len(storage.client.objects) == 1
        preview = api.client.get(endpoint, headers=api.user())
        assert preview.status_code == 200
        with Image.open(BytesIO(preview.content)) as image:
            assert image.getpixel((0, 0))[:3] == ((255, 0, 0) if color == "red" else (0, 0, 255))
    before = dict(storage.client.objects)
    storage.client.fail = True
    assert (
        api.client.put(endpoint, content=logo_bytes("green"), headers=api.user()).status_code == 503
    )
    assert api.client.delete(endpoint, headers=api.user()).status_code == 503
    assert storage.client.objects == before
    assert api.client.get(f"/clinics/{tenant}", headers=api.user()).json()["branding"]["logo_url"]
    storage.client.fail = False
    assert (
        api.client.patch(
            f"/clinics/{tenant}",
            headers=api.user(),
            json={
                "branding": {"primary_color": "#156B63", "description": "Demo", "logo_url": None}
            },
        ).status_code
        == 409
    )
    for _ in range(2):
        assert (
            api.client.delete(endpoint, headers=api.user("platform")).json()["branding"]["logo_url"]
            is None
        )
        assert not storage.client.objects
    assert api.client.get(endpoint, headers=api.user()).status_code == 404


def test_logo_validation_storage_outage_and_versioned_bucket_preserve_metadata(api):
    tenant = api.client.post("/clinics", json=body(), headers=api.user()).json()["tenant_id"]
    storage = configure_logo_storage(api)
    endpoint = f"/clinics/{tenant}/logo"
    for content, status in [
        (b"<svg></svg>", 422),
        (b"fake PNG", 422),
        (b"x" * (MAX_LOGO_BYTES + 1), 413),
    ]:
        assert api.client.put(endpoint, content=content, headers=api.user()).status_code == status
    assert not storage.client.objects
    storage.client.fail = True
    assert api.client.put(endpoint, content=logo_bytes(), headers=api.user()).status_code == 503
    assert (
        api.client.get(f"/clinics/{tenant}", headers=api.user()).json()["branding"]["logo_url"]
        is None
    )
    storage.client.fail = False
    for state in ("Enabled", "Suspended"):
        storage.client.versioning = {"Status": state}
        assert api.client.put(endpoint, content=logo_bytes(), headers=api.user()).status_code == 503
    assert not storage.client.objects


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_logo_decoder_limits_dimensions_and_normalizes_supported_images(image_format):
    with Image.open(
        BytesIO(logo_png(logo_bytes(image_format=image_format, size=(800, 400))))
    ) as image:
        assert image.format == "PNG" and image.size == (512, 256)
    from telelink_common.errors import DomainError

    with pytest.raises(DomainError):
        logo_png(logo_bytes(size=(2001, 2000)))


def test_public_doctors_enforces_clinic_state_and_forwards_scoped_request(api):
    clinic = api.client.post("/clinics", json=body(), headers=api.user()).json()
    tenant_id = clinic["tenant_id"]
    endpoint = f"/clinics/{tenant_id}/doctors"
    assert api.client.get(endpoint).status_code == 404
    activate(api, tenant_id)
    state = {"status": 200, "extra": False}

    def directory_http(request):
        assert request.url.path == f"/internal/clinics/{tenant_id}/doctors"
        assert request.url.params["limit"] == "1"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            TENANT,
            algorithms=["HS256"],
            issuer="telelink-service:tenant",
            audience="telelink-identity-doctors",
        )
        assert claims["sub"] == "tenant" and claims["exp"] - claims["iat"] == 60
        item = {"doctor_id": str(api.ids["doctor"]), "display_name": "Doctor"}
        if state["extra"]:
            item["cognito_sub"] = "private"
        return httpx.Response(state["status"], json={"items": [item], "next_cursor": "next"})

    api.app.state.identity_client.close()
    api.app.state.identity_client = IdentityClient(
        api.app.state.settings, transport=httpx.MockTransport(directory_http)
    )
    response = api.client.get(endpoint, params={"limit": 1})
    assert response.status_code == 200 and response.json()["items"] == [
        {"doctor_id": str(api.ids["doctor"]), "display_name": "Doctor"}
    ]
    state["extra"] = True
    assert api.client.get(endpoint, params={"limit": 1}).status_code == 503
    state["status"] = 422
    assert api.client.get(endpoint, params={"limit": 1, "cursor": "bad"}).status_code == 422
    state["status"] = 503
    assert api.client.get(endpoint, params={"limit": 1}).status_code == 503
    activate(api, tenant_id, membership_provisioned=False)
    assert api.client.get(endpoint).status_code == 404


def test_public_logo_only_exposes_approved_clinic_branding(api):
    clinic = api.client.post("/clinics", json=body(), headers=api.user()).json()
    tenant_id = clinic["tenant_id"]
    endpoint = f"/clinics/{tenant_id}/public-logo"
    api.app.state.logo_storage = SimpleNamespace(read=lambda tenant: b"image", close=lambda: None)
    assert api.client.get(endpoint).status_code == 404
    activate(api, tenant_id, logo_url="https://assets.example.com/logo.png")
    response = api.client.get(endpoint)
    assert response.status_code == 200 and response.content == b"image"
    assert response.headers["cache-control"] == "no-cache"
    activate(api, tenant_id, status="suspended")
    assert api.client.get(endpoint).status_code == 404
