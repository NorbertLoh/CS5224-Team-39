import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.clinics import ClinicDirectory
from app.database import create_database_engine
from app.main import create_app
from app.models import Membership, Subject
from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
CLINICS = ROOT / "dev/fixtures/telelink.json"
TENANT_A = UUID("00000000-0000-4000-8000-000000000002")
TENANT_B = UUID("00000000-0000-4000-8000-000000000025")
CURSOR_KEY = "test-cursor-secret-that-is-at-least-32-bytes"
SERVICE_KEY = "test-scheduling-secret-that-is-at-least-32-bytes"
ACTIONS = "appointment.read appointment.cancel clinical.read clinical.write medicine.ready"


def configuration(**changes):
    return Settings(
        _env_file=None,
        **(
            {
                "environment": "test",
                "auth_issuer": "http://localhost:4566/test-pool",
                "auth_jwks_url": "http://localhost:4566/test-pool/.well-known/jwks.json",
                "auth_client_id": "test-web",
                "auth_required_scopes": "openid",
                "cursor_secret": CURSOR_KEY,
                "scheduling_secret": SERVICE_KEY,
                "scheduling_actions": ACTIONS,
                "clinic_fixture_path": CLINICS,
            }
            | changes
        ),
    )


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def api_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL-backed identity API tests")
    if os.environ.get("IDENTITY_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set IDENTITY_TEST_ALLOW_RESET=1 for disposable database tests")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    try:
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        yield engine, url
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


@pytest.fixture
def api(api_database, signing_key):
    engine, url = api_database
    ids = {
        name: uuid4()
        for name in (
            "patient",
            "other_patient",
            "doctor",
            "former",
            "admin_a",
            "admin_a2",
            "admin_b",
            "platform",
            "target",
        )
    }
    subs = {name: f"actual-runtime-{uuid4()}" for name in ids}
    with Session(engine) as session, session.begin():
        for name, subject_id in ids.items():
            global_roles = (
                ["platform_admin"]
                if name == "platform"
                else (["patient"] if "patient" in name else [])
            )
            session.add(
                Subject(
                    subject_id=subject_id,
                    cognito_sub=subs[name],
                    display_name=name,
                    email=None if name == "former" else f"{name}@example.test",
                    global_roles=global_roles,
                )
            )
        session.flush()
        for name, tenant, role, status in (
            ("doctor", TENANT_A, "doctor", "active"),
            ("former", TENANT_A, "doctor", "revoked"),
            ("admin_a", TENANT_A, "clinic_admin", "active"),
            ("admin_a2", TENANT_A, "clinic_admin", "active"),
            ("admin_b", TENANT_B, "clinic_admin", "active"),
        ):
            session.add(
                Membership(subject_id=ids[name], tenant_id=tenant, roles=[role], status=status)
            )
    settings = configuration(database_url=url)
    app = create_app(settings)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def mint(name="patient", **changes):
        now = int(time.time())
        claims = {
            "sub": subs.get(name, name),
            "iss": settings.auth_issuer,
            "iat": now,
            "exp": now + 300,
            "token_use": "access",
            "client_id": "test-web",
            "scope": "openid",
        } | changes
        return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})

    def service_token(**changes):
        now = int(time.time())
        claims = {
            "iss": "telelink-service:scheduling",
            "aud": "telelink-identity-access",
            "sub": "scheduling",
            "iat": now,
            "exp": now + 60,
        } | changes
        return jwt.encode(claims, SERVICE_KEY, algorithm="HS256")

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            mint=mint,
            service_token=service_token,
            ids=ids,
            engine=engine,
            app=app,
            settings=settings,
        )
    with Session(engine) as session, session.begin():
        session.execute(delete(Membership).where(Membership.subject_id.in_(ids.values())))
        session.execute(delete(Subject).where(Subject.subject_id.in_(ids.values())))


def headers(api, name="patient", **changes):
    return {"Authorization": f"Bearer {api.mint(name, **changes)}"}


def path(tenant=TENANT_A, subject=None):
    root = f"/clinics/{tenant}/memberships"
    return f"{root}/{subject}" if subject is not None else root


def decision_body(api, name, action, tenant=TENANT_A, doctor="doctor"):
    return {
        "subject_id": str(api.ids[name]),
        "tenant_id": str(tenant),
        "action": action,
        "resource": {
            "appointment_id": str(uuid4()),
            "patient_id": str(api.ids["patient"]),
            "doctor_id": str(api.ids[doctor]),
        },
    }


def test_self_uses_persisted_roles_and_only_active_memberships(api):
    response = api.client.get(
        "/me", headers=headers(api, "doctor", **{"cognito:groups": ["platform_admin"]})
    )
    assert response.status_code == 200
    assert response.json()["subject_id"] == str(api.ids["doctor"])
    assert response.json()["global_roles"] == []
    assert response.json()["memberships"][0]["roles"] == ["doctor"]
    assert response.json()["memberships"][0]["created_at"].endswith("Z")
    assert api.client.get("/me", headers=headers(api, "former")).json()["memberships"] == []
    assert (
        api.client.get("/me", headers=headers(api, "unknown-sub")).json()["error"]["code"]
        == "identity_not_provisioned"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "http://localhost/wrong"},
        {"client_id": "other"},
        {"token_use": "id"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"sub": ""},
    ],
)
def test_public_token_claims_are_enforced(api, changes):
    response = api.client.get("/me", headers=headers(api, **changes))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_spoofed_identity_headers_and_wrong_token_types_are_rejected(api):
    for endpoint in ("/me", path()):
        response = api.client.get(
            endpoint,
            headers={
                "X-User-ID": str(api.ids["platform"]),
                "X-Tenant-ID": str(TENANT_A),
                "X-Role": "platform_admin",
            },
        )
        assert response.status_code == 401
    assert (
        api.client.get(
            "/me", headers={"Authorization": f"Bearer {api.service_token()}"}
        ).status_code
        == 401
    )
    token = api.mint()
    head, body, signature = token.split(".")
    forged = f"{head}.{body}.{('A' if signature[0] != 'A' else 'B') + signature[1:]}"
    assert api.client.get("/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert api.client.get("/me", headers=headers(api, scope="email")).status_code == 403


def test_membership_create_replace_revoke_reactivate_and_scoping(api):
    target = path(subject=api.ids["target"])
    response = api.client.put(target, json={"roles": ["doctor"]}, headers=headers(api, "admin_a"))
    assert response.status_code == 201
    original = response.json()
    response = api.client.put(
        target, json={"roles": ["doctor", "clinic_admin"]}, headers=headers(api, "admin_a")
    )
    assert response.status_code == 200
    assert response.json()["membership_id"] == original["membership_id"]
    assert response.json()["created_at"] == original["created_at"]
    for _ in range(2):
        response = api.client.delete(target, headers=headers(api, "admin_a"))
        assert response.status_code == 204 and response.content == b""
    assert api.client.get("/me", headers=headers(api, "target")).json()["memberships"] == []
    response = api.client.put(target, json={"roles": ["doctor"]}, headers=headers(api, "admin_a"))
    assert response.json()["membership_id"] == original["membership_id"]
    assert response.json()["status"] == "active"
    assert (
        api.client.put(
            target, json={"roles": ["clinic_admin"]}, headers=headers(api, "admin_b")
        ).status_code
        == 404
    )
    assert (
        api.client.get(
            path(), headers=headers(api, "patient", **{"cognito:groups": ["clinic_admin"]})
        ).status_code
        == 404
    )
    assert (
        api.client.put(
            path(subject=uuid4()), json={"roles": ["doctor"]}, headers=headers(api, "admin_a")
        ).status_code
        == 404
    )
    assert api.client.get(path(uuid4()), headers=headers(api, "platform")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"roles": []},
        {"roles": ["doctor", "doctor"]},
        {"roles": ["platform_admin"]},
        {"roles": ["doctor"], "status": "active"},
        {"roles": ["doctor"], "global_roles": ["platform_admin"]},
    ],
)
def test_membership_body_validation(api, body):
    response = api.client.put(
        path(subject=api.ids["target"]), json=body, headers=headers(api, "admin_a")
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]


def test_email_assignment_is_normalized_idempotent_and_reactivates(api):
    body = {"email": "  TARGET@EXAMPLE.TEST  ", "roles": ["doctor"]}
    response = api.client.post(path(), json=body, headers=headers(api, "admin_a"))
    assert response.status_code == 201
    original = response.json()
    assert original["subject_id"] == str(api.ids["target"])
    assert original["subject"] == {"display_name": "target", "email": "target@example.test"}
    repeated = api.client.post(path(), json=body, headers=headers(api, "admin_a"))
    assert repeated.status_code == 200
    assert repeated.json()["membership_id"] == original["membership_id"]
    api.client.delete(path(subject=api.ids["target"]), headers=headers(api, "admin_a"))
    restored = api.client.post(path(), json=body, headers=headers(api, "platform"))
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["membership_id"] == original["membership_id"]


def test_membership_list_includes_names_and_optional_email_without_cognito_sub(api):
    response = api.client.get(path(), headers=headers(api, "admin_a"))
    assert response.status_code == 200
    rows = {item["subject_id"]: item for item in response.json()["items"]}
    assert rows[str(api.ids["doctor"])]["subject"] == {
        "display_name": "doctor",
        "email": "doctor@example.test",
    }
    assert rows[str(api.ids["former"])]["subject"] == {
        "display_name": "former",
        "email": None,
    }
    assert "cognito_sub" not in response.text


@pytest.mark.parametrize("actor", ["patient", "doctor", "former", "admin_b"])
def test_email_assignment_rejects_unrelated_callers_without_directory_access(api, actor):
    for email in ("target@example.test", "missing@example.test"):
        response = api.client.post(
            path(), json={"email": email, "roles": ["doctor"]}, headers=headers(api, actor)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    with Session(api.engine) as session:
        assert (
            session.scalar(select(Membership).where(Membership.subject_id == api.ids["target"]))
            is None
        )


def test_email_assignment_unknown_validation_and_last_admin(api):
    response = api.client.post(
        path(),
        json={"email": "missing@example.test", "roles": ["doctor"]},
        headers=headers(api, "admin_a"),
    )
    assert response.status_code == 404
    for email in ("not-email", "a@", "a b@example.test", "a" * 255 + "@example.test"):
        response = api.client.post(
            path(), json={"email": email, "roles": ["doctor"]}, headers=headers(api, "admin_a")
        )
        assert response.status_code == 422
    api.client.delete(path(subject=api.ids["admin_a2"]), headers=headers(api, "platform"))
    response = api.client.post(
        path(),
        json={"email": "admin_a@example.test", "roles": ["doctor"]},
        headers=headers(api, "platform"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_clinic_admin"


def test_last_admin_and_concurrent_removals(api):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda name: api.client.delete(
                    path(subject=api.ids[name]), headers=headers(api, "platform")
                ),
                ["admin_a", "admin_a2"],
            )
        )
    assert sorted(response.status_code for response in responses) == [204, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "last_clinic_admin"
    )
    with Session(api.engine) as session:
        surviving = session.scalar(
            select(Membership).where(
                Membership.tenant_id == TENANT_A,
                Membership.status == "active",
                Membership.roles.any("clinic_admin"),
            )
        )
        survivor_id = surviving.subject_id
    response = api.client.put(
        path(subject=survivor_id), json={"roles": ["doctor"]}, headers=headers(api, "platform")
    )
    assert response.status_code == 409


def test_pagination_signed_scopes_filter_expiry_and_fresh_authorization(api):
    first = api.client.get(path(), params={"limit": 1}, headers=headers(api, "admin_a")).json()
    cursor = first["next_cursor"]
    assert cursor and len(first["items"]) == 1
    second = api.client.get(
        path(), params={"limit": 1, "cursor": cursor}, headers=headers(api, "admin_a")
    )
    assert second.status_code == 200
    assert second.json()["items"][0]["membership_id"] != first["items"][0]["membership_id"]
    for name, tenant, params in (
        ("admin_a2", TENANT_A, {"cursor": cursor}),
        ("admin_a", TENANT_A, {"cursor": cursor, "status": "active"}),
        ("platform", TENANT_B, {"cursor": cursor}),
        ("admin_a", TENANT_A, {"cursor": cursor + "x"}),
        ("admin_a", TENANT_A, {"limit": 0}),
    ):
        assert (
            api.client.get(path(tenant), params=params, headers=headers(api, name)).status_code
            == 422
        )
    claims = jwt.decode(cursor, CURSOR_KEY, algorithms=["HS256"], audience="memberships")
    expired = jwt.encode(claims | {"iat": 1, "exp": 2}, CURSOR_KEY, algorithm="HS256")
    assert (
        api.client.get(
            path(), params={"cursor": expired}, headers=headers(api, "admin_a")
        ).status_code
        == 422
    )
    revoked = api.client.get(
        path(), params={"status": "revoked"}, headers=headers(api, "admin_a")
    ).json()
    assert revoked["next_cursor"] is None and len(revoked["items"]) == 1
    assert (
        api.client.delete(
            path(subject=api.ids["admin_a"]), headers=headers(api, "admin_a2")
        ).status_code
        == 204
    )
    assert (
        api.client.get(
            path(), params={"cursor": cursor}, headers=headers(api, "admin_a")
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "name, action, allowed, reason",
    [
        ("patient", "appointment.read", True, "own_appointment"),
        ("patient", "appointment.cancel", True, "own_appointment"),
        ("patient", "clinical.read", True, "own_appointment"),
        ("patient", "clinical.write", False, "not_authorized"),
        ("patient", "medicine.ready", False, "not_authorized"),
        ("other_patient", "appointment.read", False, "not_authorized"),
        ("doctor", "clinical.write", True, "assigned_doctor"),
        ("doctor", "clinical.read", True, "assigned_doctor"),
        ("doctor", "appointment.read", True, "assigned_doctor"),
        ("doctor", "appointment.cancel", False, "not_authorized"),
        ("admin_a", "appointment.read", True, "clinic_admin"),
        ("admin_a", "appointment.cancel", True, "clinic_admin"),
        ("admin_a", "medicine.ready", True, "clinic_admin"),
        ("admin_a", "clinical.read", False, "not_authorized"),
        ("admin_a", "clinical.write", False, "not_authorized"),
        ("admin_b", "appointment.read", False, "not_authorized"),
        ("platform", "appointment.read", True, "platform_admin"),
        ("platform", "appointment.cancel", False, "not_authorized"),
        ("platform", "clinical.read", False, "not_authorized"),
        ("platform", "clinical.write", False, "not_authorized"),
    ],
)
def test_access_decision_matrix(api, name, action, allowed, reason):
    response = api.client.post(
        "/access-decisions",
        json=decision_body(api, name, action),
        headers={"Authorization": f"Bearer {api.service_token()}"},
    )
    assert response.status_code == 200
    assert response.json() == {"allowed": allowed, "reason": reason}


def test_access_decisions_reject_untrusted_and_stale_context(api):
    body = decision_body(api, "patient", "clinical.read")
    for request_headers in ({}, headers(api, "platform"), {"X-Service-ID": "scheduling"}):
        assert (
            api.client.post("/access-decisions", json=body, headers=request_headers).status_code
            == 401
        )
    service_headers = {"Authorization": f"Bearer {api.service_token()}"}
    for invalid in (
        body | {"action": "unknown"},
        body | {"resource": {}},
        body | {"extra": "ignored"},
    ):
        assert (
            api.client.post("/access-decisions", json=invalid, headers=service_headers).status_code
            == 422
        )
    for name, tenant, doctor in (
        ("former", TENANT_A, "former"),
        ("doctor", TENANT_B, "doctor"),
        ("doctor", TENANT_A, "target"),
    ):
        response = api.client.post(
            "/access-decisions",
            json=decision_body(api, name, "clinical.write", tenant, doctor),
            headers=service_headers,
        )
        assert response.json() == {"allowed": False, "reason": "not_authorized"}
    assert (
        api.client.delete(
            path(subject=api.ids["doctor"]), headers=headers(api, "admin_a")
        ).status_code
        == 204
    )
    assert (
        api.client.post(
            "/access-decisions",
            json=decision_body(api, "doctor", "clinical.write"),
            headers=service_headers,
        ).json()["allowed"]
        is False
    )
    api.app.state.settings.scheduling_actions = "appointment.read"
    assert (
        api.client.post("/access-decisions", json=body, headers=service_headers).status_code == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"sub": "tenant"},
        {"iss": "other"},
        {"aud": "other"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"exp": int(time.time()) + 3600},
    ],
)
def test_service_token_claims_are_enforced(api, changes):
    response = api.client.post(
        "/access-decisions",
        json=decision_body(api, "patient", "clinical.read"),
        headers={"Authorization": f"Bearer {api.service_token(**changes)}"},
    )
    assert response.status_code == 401


def test_safe_errors_correlation_and_clinic_adapter_fails_closed(api):
    response = api.client.get(
        "/me", headers={"X-Request-ID": "api-test-01", "X-User-ID": "secret-value"}
    )
    assert response.headers["X-Request-ID"] == "api-test-01"
    assert response.json()["error"]["request_id"] == "api-test-01"
    assert "secret-value" not in response.text
    api.app.state.clinic_directory.tenant_ids = None
    assert (
        api.client.put(
            path(subject=api.ids["target"]),
            json={"roles": ["doctor"]},
            headers=headers(api, "admin_a"),
        ).status_code
        == 503
    )
    assert api.client.get("/health/ready").status_code == 200


def test_concurrent_puts_create_one_membership(api):
    target = path(subject=api.ids["target"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: api.client.put(
                    target, json={"roles": ["doctor"]}, headers=headers(api, "admin_a")
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert responses[0].json()["membership_id"] == responses[1].json()["membership_id"]


def test_live_clinic_validation_and_authorization(api):
    calls = []
    key = "identity-secret-for-tests-at-least-32-bytes"
    settings = configuration(
        clinic_fixture_path=None, tenant_url="http://tenant.test/api/v1/tenant", identity_secret=key
    )

    def lookup(request):
        calls.append(request)
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            key,
            algorithms=["HS256"],
            issuer="telelink-service:identity",
            audience="telelink-tenant-memberships",
        )
        assert claims["sub"] == "identity" and claims["exp"] - claims["iat"] == 60
        assert request.headers["X-Request-ID"]
        assert request.url.path.startswith("/api/v1/tenant/internal/clinics/")
        tenant = request.url.path.split("/")[-2]
        return httpx.Response(200, json={"tenant_id": tenant})

    api.app.state.clinic_directory.close()
    api.app.state.clinic_directory = ClinicDirectory(
        settings, transport=httpx.MockTransport(lookup)
    )
    for name in ("patient", "doctor", "admin_b", "former"):
        assert api.client.get(path(), headers=headers(api, name)).status_code == 404
    assert not calls
    target = path(subject=api.ids["target"])
    assert (
        api.client.put(
            target, json={"roles": ["doctor"]}, headers=headers(api, "admin_a")
        ).status_code
        == 201
    )
    assert api.client.get(path(), headers=headers(api, "platform")).status_code == 200
    assert api.client.delete(target, headers=headers(api, "admin_a")).status_code == 204
    assert (
        api.client.put(
            target, json={"roles": ["clinic_admin"]}, headers=headers(api, "admin_a")
        ).status_code
        == 200
    )
    assert len(calls) == 4


@pytest.mark.parametrize("outcome", [404, 401, 500, 302, "timeout", "mismatch", "malformed"])
def test_live_clinic_failures_do_not_write_memberships(api, outcome):
    def lookup(request):
        if outcome == "timeout":
            raise httpx.ReadTimeout("private upstream detail", request=request)
        if outcome == "mismatch":
            return httpx.Response(200, json={"tenant_id": str(uuid4())})
        if outcome == "malformed":
            return httpx.Response(200, json=[])
        return httpx.Response(outcome, text="private upstream detail")

    api.app.state.clinic_directory = ClinicDirectory(
        configuration(
            clinic_fixture_path=None,
            tenant_url="http://tenant.test",
            identity_secret="identity-secret-for-tests-at-least-32-bytes",
        ),
        transport=httpx.MockTransport(lookup),
    )
    response = api.client.put(
        path(subject=api.ids["target"]), json={"roles": ["doctor"]}, headers=headers(api, "admin_a")
    )
    assert response.status_code == (404 if outcome == 404 else 503)
    assert "private upstream detail" not in response.text
    with Session(api.engine) as session:
        assert (
            session.scalar(select(Membership).where(Membership.subject_id == api.ids["target"]))
            is None
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_url": "http://tenant.test"},
        {"tenant_url": "http://tenant.test", "identity_secret": "x" * 32},
        {"tenant_url": "http://user:password@tenant.test", "clinic_fixture_path": None},
        {"identity_secret": CURSOR_KEY},
    ],
)
def test_live_clinic_configuration_rejects_unsafe_settings(changes):
    with pytest.raises(ValidationError):
        configuration(**changes)


def test_missing_dependencies_keys_cors_and_error_sanitization(api):
    from jwt.exceptions import PyJWKClientConnectionError

    def offline():
        raise PyJWKClientConnectionError("private-key-provider-information")

    api.app.state.token_verifier.jwks.fetch_data = offline
    api.app.state.token_verifier.jwks.jwk_set_cache = None
    response = api.client.get("/me", headers=headers(api))
    assert response.status_code == 503
    assert "private-key-provider-information" not in response.text
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert (
            client.get("/me", headers={"Authorization": "Bearer unconfigured"}).status_code == 503
        )
    with TestClient(
        create_app(configuration(database_url=None, cors_origins=["http://localhost:5173"]))
    ) as client:
        response = client.options(
            "/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        response = client.options(
            "/me",
            headers={"Origin": "http://attacker.example", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code == 400


@pytest.mark.parametrize(
    "changes",
    [
        {"cursor_secret": "short"},
        {"scheduling_secret": "short"},
        {"scheduling_secret": CURSOR_KEY},
        {"scheduling_actions": "clinical.delete"},
        {"environment": "production"},
        {"cors_origins": ["*"]},
    ],
)
def test_invalid_api_configuration(changes):
    with pytest.raises(ValidationError):
        configuration(**changes)


TENANT_KEY = "test-tenant-provisioning-secret-at-least-32-bytes"


def tenant_token(**changes):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "telelink-service:tenant",
            "aud": "telelink-identity-provisioning",
            "sub": "tenant",
            "iat": now,
            "exp": now + 60,
        }
        | changes,
        TENANT_KEY,
        algorithm="HS256",
    )


def test_creator_provisioning_is_scoped_and_idempotent(api):
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    tenant_id = uuid4()
    body = {"tenant_id": str(tenant_id), "subject_id": str(api.ids["patient"])}
    credential = {"Authorization": "Bearer " + tenant_token()}
    endpoint = "/internal/clinic-creators"
    assert api.client.put(endpoint, json=body).status_code == 401
    assert api.client.put(endpoint, json=body, headers=headers(api)).status_code == 401
    assert (
        api.client.put(
            endpoint, json=body, headers={"Authorization": "Bearer " + api.service_token()}
        ).status_code
        == 401
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(lambda _: api.client.put(endpoint, json=body, headers=credential), range(4))
        )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["membership_id"] for response in responses}) == 1
    first = responses[0]
    assert first.status_code == 200 and first.json()["roles"] == ["clinic_admin"]
    repeated = api.client.put(endpoint, json=body, headers=credential)
    assert repeated.status_code == 200
    assert repeated.json()["membership_id"] == first.json()["membership_id"]
    assert repeated.json()["updated_at"] == first.json()["updated_at"]
    assert (
        api.client.put(
            endpoint, json=body | {"roles": ["platform_admin"]}, headers=credential
        ).status_code
        == 422
    )
    assert (
        api.client.put(
            endpoint, json=body | {"subject_id": str(uuid4())}, headers=credential
        ).status_code
        == 404
    )
    with Session(api.engine) as session, session.begin():
        membership = session.get(Membership, UUID(first.json()["membership_id"]))
        membership.status = "revoked"
    assert api.client.put(endpoint, json=body, headers=credential).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "telelink-identity-access"},
        {"sub": "scheduling"},
        {"exp": int(time.time()) - 1},
        {"exp": int(time.time()) + 3600},
        {"iat": "invalid"},
    ],
)
def test_creator_provisioning_rejects_wrong_service_credentials(api, changes):
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    result = api.client.put(
        "/internal/clinic-creators",
        json={"tenant_id": str(uuid4()), "subject_id": str(api.ids["patient"])},
        headers={"Authorization": "Bearer " + tenant_token(**changes)},
    )
    assert result.status_code == 401


def test_doctor_directory_service_scope_pagination_and_revocation(api):
    api.app.state.settings.tenant_secret = SecretStr(TENANT_KEY)
    endpoint = f"/internal/clinics/{TENANT_A}/doctors"
    credential = {"Authorization": "Bearer " + tenant_token(aud="telelink-identity-doctors")}
    assert api.client.get(endpoint).status_code == 401
    assert api.client.get(endpoint, headers=headers(api)).status_code == 401
    assert (
        api.client.get(endpoint, headers={"Authorization": "Bearer " + tenant_token()}).status_code
        == 401
    )
    with Session(api.engine) as session, session.begin():
        session.add(Membership(subject_id=api.ids["target"], tenant_id=TENANT_A, roles=["doctor"]))
        session.add(Membership(subject_id=api.ids["patient"], tenant_id=TENANT_B, roles=["doctor"]))
    first = api.client.get(endpoint, params={"limit": 1}, headers=credential).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = api.client.get(
        endpoint, params={"cursor": first["next_cursor"]}, headers=credential
    ).json()
    summaries = first["items"] + second["items"]
    assert {item["doctor_id"] for item in summaries} == {
        str(api.ids["doctor"]),
        str(api.ids["target"]),
    }
    assert all(set(item) == {"doctor_id", "display_name"} for item in summaries)
    assert (
        api.client.get(
            f"/internal/clinics/{TENANT_B}/doctors",
            params={"cursor": first["next_cursor"]},
            headers=credential,
        ).status_code
        == 422
    )
    assert (
        api.client.get(
            endpoint, params={"cursor": first["next_cursor"] + "x"}, headers=credential
        ).status_code
        == 422
    )
    with Session(api.engine) as session, session.begin():
        membership = session.scalar(
            select(Membership).where(
                Membership.subject_id == api.ids["doctor"], Membership.tenant_id == TENANT_A
            )
        )
        membership.status = "revoked"
    assert api.client.get(endpoint, headers=credential).json()["items"] == [
        {"doctor_id": str(api.ids["target"]), "display_name": "target"}
    ]
