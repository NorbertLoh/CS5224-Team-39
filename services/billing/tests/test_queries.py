"""B05 real PostgreSQL reads with signed tokens and current identity transport."""

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text
from telelink_common.access import IdentityClient

from app.main import create_app
from app.settings import Settings
from tests.helpers import insert, payment_values

CURSOR_SECRET = "b05-independent-cursor-secret-at-least-32-bytes"


@pytest.fixture
def api(database, database_url):
    with database.begin() as connection:
        connection.execute(text("TRUNCATE billing.payments, billing.checkout_attempts CASCADE"))
    patient, other, tenant, foreign = (uuid4() for _ in range(4))
    state = {"roles": ["patient"], "memberships": [], "identity_status": 200}
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        auth_issuer="http://localhost/b05-pool",
        auth_jwks_url="http://localhost/jwks",
        auth_client_id="b05-web",
        identity_url="http://identity.test",
        cursor_secret=CURSOR_SECRET,
    )
    app = create_app(settings)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="b05", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def identity(request):
        if state["identity_status"] != 200:
            return httpx.Response(state["identity_status"])
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            key.public_key(),
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
        )
        subject = claims["sub"]
        now = datetime.now(timezone.utc).isoformat()
        return httpx.Response(
            200,
            json={
                "subject_id": subject,
                "cognito_sub": subject,
                "display_name": "Synthetic",
                "global_roles": state["roles"],
                "memberships": [
                    {
                        "membership_id": str(uuid4()),
                        "subject_id": subject,
                        "tenant_id": str(t),
                        "roles": roles,
                        "status": status,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for t, roles, status in state["memberships"]
                ],
            },
        )

    def headers(subject=patient, **changes):
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": settings.auth_issuer,
                "sub": str(subject),
                "iat": now,
                "exp": now + 300,
                "token_use": "access",
                "client_id": "b05-web",
            }
            | changes,
            key,
            algorithm="RS256",
            headers={"kid": "b05"},
        )
        return {"Authorization": "Bearer " + token}

    def seed(**overrides):
        values = payment_values(patient_id=patient, tenant_id=tenant) | overrides
        return insert(database, values)

    with TestClient(app) as client:
        app.state.identity_client.close()
        app.state.identity_client = IdentityClient(
            settings, transport=httpx.MockTransport(identity)
        )
        yield client, headers, seed, state, tenant, foreign, patient, other, app


def ids(response):
    assert response.status_code == 200, response.text
    return {row["payment_id"] for row in response.json()["items"]}


def test_patient_ownership_and_projection(api):
    client, headers, seed, _, tenant, foreign, patient, other, _ = api
    own = seed()
    across_clinic = seed(tenant_id=foreign, status="failed")
    hidden = seed(patient_id=other)
    assert ids(client.get("/payments", headers=headers())) == {str(own), str(across_clinic)}
    assert ids(client.get("/payments", params={"tenant_id": str(tenant)}, headers=headers())) == {
        str(own)
    }
    for payment_id in (own, across_clinic):
        response = client.get(f"/payments/{payment_id}", headers=headers())
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["amount"] == {"amount_minor": 2500, "currency": "SGD"}
        assert "provider" not in response.text
        assert "checkout_url" not in response.text
    hidden_response = client.get(f"/payments/{hidden}", headers=headers())
    absent_response = client.get(f"/payments/{uuid4()}", headers=headers())
    assert hidden_response.status_code == absent_response.status_code == 404
    assert hidden_response.json()["error"]["message"] == absent_response.json()["error"]["message"]
    assert client.get(f"/payments/{own}", headers=headers(other)).status_code == 404


@pytest.mark.parametrize(
    "roles,membership,expected",
    [
        ([], ["clinic_admin"], True),
        ([], ["doctor"], False),
        (["patient"], ["doctor"], False),
        (["platform_admin"], [], True),
    ],
)
def test_role_scopes(api, roles, membership, expected):
    client, headers, seed, state, tenant, foreign, _, other, _ = api
    local = seed(patient_id=other)
    remote = seed(patient_id=other, tenant_id=foreign)
    state["roles"] = roles
    state["memberships"] = [(tenant, membership, "active")] if membership else []
    response = client.get("/payments", headers=headers())
    if expected:
        wanted = {str(local), str(remote)} if "platform_admin" in roles else {str(local)}
        assert ids(response) == wanted
        assert client.get(f"/payments/{local}", headers=headers()).status_code == 200
        assert client.get(f"/payments/{remote}", headers=headers()).status_code == (
            200 if "platform_admin" in roles else 404
        )
    elif roles:
        assert ids(response) == set()
        assert client.get(f"/payments/{local}", headers=headers()).status_code == 404
    else:
        assert response.status_code == 403
        assert client.get(f"/payments/{local}", headers=headers()).status_code == 404


def test_combined_roles_and_revocation(api):
    client, headers, seed, state, tenant, foreign, _, other, _ = api
    own_remote = seed(tenant_id=foreign)
    admin_local = seed(patient_id=other)
    seed(patient_id=other, tenant_id=foreign)
    state["memberships"] = [(tenant, ["clinic_admin"], "active")]
    assert ids(client.get("/payments", headers=headers())) == {str(own_remote), str(admin_local)}
    state["memberships"] = [(tenant, ["clinic_admin"], "revoked")]
    assert ids(client.get("/payments", headers=headers())) == {str(own_remote)}
    assert client.get(f"/payments/{admin_local}", headers=headers()).status_code == 404
    state["roles"] = []
    assert client.get("/payments", headers=headers()).status_code == 403


def test_filters_and_pagination_with_equal_timestamps(api):
    client, headers, seed, _, tenant, _, _, other, _ = api
    instant = datetime(2026, 10, 1, tzinfo=timezone.utc)
    wanted = sorted(str(seed(created_at=instant)) for _ in range(4))
    seed(patient_id=other, created_at=instant)
    seed(status="failed", created_at=instant)
    medication = seed(
        purpose="medication_delivery", appointment_id=None, order_id=uuid4(), quote_id=uuid4()
    )
    params = {"limit": 2, "purpose": "consultation", "status": "pending", "tenant_id": str(tenant)}
    first = client.get("/payments", params=params, headers=headers())
    assert first.status_code == 200, first.text
    body = first.json()
    assert [p["payment_id"] for p in body["items"]] == wanted[:2]
    second = client.get(
        "/payments", params=params | {"cursor": body["next_cursor"]}, headers=headers()
    )
    assert [p["payment_id"] for p in second.json()["items"]] == wanted[2:]
    assert second.json()["next_cursor"] is None
    assert ids(
        client.get("/payments", params={"purpose": "medication_delivery"}, headers=headers())
    ) == {str(medication)}


@pytest.mark.parametrize("change", ["tamper", "expired", "subject", "filter", "access", "order"])
def test_cursor_rejected_outside_scope(api, change):
    client, headers, seed, state, tenant, _, _, other, _ = api
    seed()
    seed()
    token = client.get("/payments", params={"limit": 1}, headers=headers()).json()["next_cursor"]
    caller, params = headers(), {"cursor": token}
    if change == "tamper":
        params["cursor"] = "bad." + token
    elif change in {"expired", "order"}:
        claims = jwt.decode(token, CURSOR_SECRET, algorithms=["HS256"], audience="payments")
        if change == "expired":
            claims["iat"], claims["exp"] = 1, 2
        else:
            claims["scope"]["order"] = "descending"
        params["cursor"] = jwt.encode(claims, CURSOR_SECRET, algorithm="HS256")
    elif change == "subject":
        caller = headers(other)
    elif change == "filter":
        params["status"] = "succeeded"
    else:
        state["memberships"] = [(tenant, ["clinic_admin"], "active")]
    response = client.get("/payments", params=params, headers=caller)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["field"] == "query.cursor"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": "bad"},
        {"cursor": ""},
        {"tenant_id": "bad"},
        {"purpose": "other"},
        {"status": "paid"},
    ],
)
def test_bad_filters(api, params):
    response = api[0].get("/payments", params=params, headers=api[1]())
    assert response.status_code == 422


def test_empty_and_unconfigured_storage_or_cursor(api):
    client, headers, _, _, _, _, _, _, app = api
    assert client.get("/payments", headers=headers()).json() == {"items": [], "next_cursor": None}
    app.state.settings.cursor_secret = None
    assert client.get("/payments", headers=headers()).status_code == 503
    engine = app.state.database_engine
    try:
        app.state.database_engine = None
        assert client.get("/payments", headers=headers()).status_code == 503
        assert client.get("/commission-totals", headers=headers()).status_code == 503
    finally:
        app.state.database_engine = engine


@pytest.mark.parametrize(
    "path", ["/payments", "/payments/00000000-0000-4000-8000-000000000001", "/commission-totals"]
)
def test_authentication_and_identity_fail_closed(api, path):
    client, headers, _, state, *_ = api
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(exp=1)).status_code == 401
    assert client.get(path, headers=headers(token_use="id")).status_code == 401
    state["identity_status"] = 503
    assert client.get(path, headers=headers()).status_code == 503


def test_commission_totals_scope_states_and_snapshots(api):
    client, headers, seed, state, tenant, foreign, _, other, _ = api
    seed(status="succeeded", patient_id=other)
    seed(
        status="succeeded",
        commission_bps=2000,
        commission_amount_minor=500,
        clinic_amount_minor=2000,
    )
    seed(
        status="succeeded",
        purpose="medication_delivery",
        appointment_id=None,
        order_id=uuid4(),
        quote_id=uuid4(),
        amount_minor=3000,
        delivery_fee_minor=500,
        clinic_amount_minor=2750,
    )
    for status in ("pending", "failed", "refund_pending", "refunded", "refund_failed"):
        seed(status=status)
    seed(status="succeeded", resolution="refund_required")
    seed(status="succeeded", tenant_id=foreign)
    assert client.get("/commission-totals", headers=headers()).status_code == 403
    state["memberships"] = [(tenant, ["clinic_admin"], "active")]
    response = client.get("/commission-totals", headers=headers())
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "payment_count": 3,
        "amount": {"amount_minor": 8000, "currency": "SGD"},
        "commission_amount": {"amount_minor": 1000, "currency": "SGD"},
        "clinic_amount": {"amount_minor": 7000, "currency": "SGD"},
    }
    assert (
        client.get(
            "/commission-totals", params={"tenant_id": str(foreign)}, headers=headers()
        ).json()["payment_count"]
        == 0
    )
    assert (
        client.get(
            "/commission-totals", params={"purpose": "consultation"}, headers=headers()
        ).json()["commission_amount"]["amount_minor"]
        == 750
    )
    state["roles"] = ["platform_admin"]
    assert client.get("/commission-totals", headers=headers()).json()["payment_count"] == 4
    state["roles"] = []
    state["memberships"] = [(tenant, ["clinic_admin"], "revoked")]
    assert client.get("/commission-totals", headers=headers()).status_code == 403
    state["memberships"] = [(tenant, ["doctor"], "active")]
    assert client.get("/commission-totals", headers=headers()).status_code == 403


def test_totals_empty_and_safe_integer_boundary(api):
    client, headers, seed, state, *_ = api
    state["roles"] = ["platform_admin"]
    body = client.get("/commission-totals", headers=headers()).json()
    assert body["payment_count"] == body["amount"]["amount_minor"] == 0
    maximum = 9007199254740991
    seed(
        status="succeeded",
        amount_minor=maximum,
        commissionable_minor=maximum,
        commission_bps=0,
        commission_amount_minor=0,
        clinic_amount_minor=maximum,
    )
    assert (
        client.get("/commission-totals", headers=headers()).json()["amount"]["amount_minor"]
        == maximum
    )
    seed(status="succeeded")
    response = client.get("/commission-totals", headers=headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "totals_limit_exceeded"


def test_cursor_secret_configuration():
    with pytest.raises(ValueError, match="cursor_secret"):
        Settings(_env_file=None, cursor_secret="short")
