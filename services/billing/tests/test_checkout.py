import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from telelink_common.access import IdentityClient
from telelink_common.service_auth import service_token

from app.expire_checkouts import expire_due
from app.main import create_app
from app.models import CheckoutAttempt, Payment
from app.provider import StripeCheckout
from app.settings import Settings
from app.upstream import CheckoutSources

SCHEDULING = "b02-scheduling-secret-with-at-least-32-bytes"
TENANT = "b02-tenant-secret-with-at-least-32-bytes"


@pytest.fixture
def api(database, database_url):
    # database_url fixture already requires explicit disposable reset consent.
    # Worker tests must not sweep operations left by a previous local test run.
    with database.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE billing.checkout_keys, billing.checkout_attempts, billing.payments, "
                "billing.medication_checkout_keys, billing.medication_checkout_attempts, "
                "billing.refund_attempts"
            )
        )
    patient, other, tenant, appointment = uuid4(), uuid4(), uuid4(), uuid4()
    expires = datetime.now(timezone.utc) + timedelta(minutes=9)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=database_url,
        auth_issuer="http://localhost/test-pool",
        auth_jwks_url="http://localhost/jwks",
        auth_client_id="test-web",
        identity_url="http://identity.test",
        scheduling_url="http://scheduling.test",
        scheduling_secret=SCHEDULING,
        tenant_url="http://tenant.test",
        tenant_secret=TENANT,
        stripe_secret_key="sk_test_synthetic",
        stripe_destinations={tenant: "acct_synthetic"},
    )
    state = {
        "price": 5000,
        "rate": 1000,
        "provider_calls": [],
        "sessions": {},
        "reserve_error": None,
        "profile_error": None,
        "timeout": False,
        "rejected": False,
        "malformed": None,
        "role": "patient",
        "paid": False,
    }
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = create_app(settings)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test", use="sig", alg="RS256")
    app.state.token_verifier.jwks.fetch_data = lambda: {"keys": [jwk]}

    def identity(request):
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            key.public_key(),
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
        )
        return httpx.Response(
            200,
            json={
                "subject_id": claims["sub"],
                "cognito_sub": claims["sub"],
                "display_name": "Synthetic",
                "memberships": [],
                "global_roles": [state["role"]] if state["role"] else [],
            },
        )

    def sources(request):
        scheduling = request.url.host == "scheduling.test"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            SCHEDULING if scheduling else TENANT,
            algorithms=["HS256"],
            issuer="telelink-service:billing",
            audience="telelink-scheduling-billing" if scheduling else "telelink-tenant-billing",
        )
        assert claims["sub"] == "billing" and claims["exp"] - claims["iat"] == 60
        error = state["reserve_error" if scheduling else "profile_error"]
        if error:
            return httpx.Response(error, json={"error": {"code": "hold_expired"}})
        if not scheduling:
            return httpx.Response(
                200,
                json={
                    "tenant_id": str(tenant),
                    "status": "active",
                    "commission_bps": state["rate"],
                },
            )
        data = json.loads(request.content)
        if data["patient_id"] != str(patient):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "appointment_id": request.url.path.split("/")[3],
                "tenant_id": str(tenant),
                "patient_id": str(patient),
                "payment_id": data["payment_id"],
                "status": "pending_payment",
                "hold_expires_at": expires.isoformat(),
                "consultation_price": {"amount_minor": state["price"], "currency": "SGD"},
            },
        )

    def stripe(request):
        state["provider_calls"].append(request)
        assert request.headers["Authorization"] == "Bearer sk_test_synthetic"
        if request.method == "POST" and request.url.path == "/v1/checkout/sessions":
            if state["rejected"]:
                return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
            fields = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            operation = request.headers["Idempotency-Key"]
            value = state["sessions"].setdefault(
                operation,
                {
                    "id": "cs_test_" + fields["client_reference_id"].replace("-", ""),
                    "livemode": False,
                    "client_reference_id": fields["client_reference_id"],
                    "amount_total": int(fields["line_items[0][price_data][unit_amount]"]),
                    "currency": "sgd",
                    "metadata": {"payment_id": fields["metadata[payment_id]"]},
                    "url": "https://checkout.stripe.com/c/pay/synthetic",
                    "status": "open",
                    "payment_status": "unpaid",
                },
            )
            if state["timeout"]:
                raise httpx.ReadTimeout("Synthetic lost response", request=request)
            return httpx.Response(200, json=value | (state["malformed"] or {}))
        value = next(v for v in state["sessions"].values() if v["id"] in request.url.path)
        if state["paid"]:
            value.update(status="complete", payment_status="paid")
        elif request.method == "POST":
            value["status"] = "expired"
        return httpx.Response(200, json=value)

    def user(subject=patient, **changes):
        current = int(time.time())
        token = jwt.encode(
            {
                "iss": settings.auth_issuer,
                "sub": str(subject),
                "iat": current,
                "exp": current + 300,
                "token_use": "access",
                "client_id": "test-web",
            }
            | changes,
            key,
            algorithm="RS256",
            headers={"kid": "test"},
        )
        return {"Authorization": "Bearer " + token}

    with TestClient(app) as client:
        app.state.identity_client.close()
        app.state.sources.close()
        app.state.provider.close()
        app.state.identity_client = IdentityClient(
            settings, transport=httpx.MockTransport(identity)
        )
        app.state.sources = CheckoutSources(settings, transport=httpx.MockTransport(sources))
        app.state.provider = StripeCheckout(settings, transport=httpx.MockTransport(stripe))
        yield client, user, appointment, patient, other, tenant, expires, state, database


def checkout(api, key="test", appointment=None, subject=None, extra=None):
    client, user, own, patient, *_ = api
    return client.post(
        "/consultation-checkouts",
        headers=user(subject or patient) | {"Idempotency-Key": key},
        json={"appointment_id": str(appointment or own)} | (extra or {}),
    )


def test_trusted_snapshot_and_replay(api):
    result = checkout(api)
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["payment"]["amount"] == {"amount_minor": 5000, "currency": "SGD"}
    assert body["payment"]["commission_amount"]["amount_minor"] == 500
    assert body["payment"]["clinic_amount"]["amount_minor"] == 4500
    assert UUID(body["payment"]["appointment_id"]) == api[2]
    assert "provider" not in json.dumps(body)
    assert result.headers["cache-control"] == "no-store"
    api[7]["rate"] = 9000
    replay = checkout(api)
    assert replay.status_code == 200 and replay.json() == body
    alias = checkout(api, "another")
    assert alias.status_code == 200 and alias.json() == body
    assert len(api[7]["provider_calls"]) == 1
    fields = parse_qs(api[7]["provider_calls"][0].content.decode())
    assert fields["payment_intent_data[application_fee_amount]"] == ["500"]
    assert fields["payment_intent_data[transfer_data][destination]"] == ["acct_synthetic"]
    assert fields["metadata[appointment_id]"] == [str(api[2])]


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_creates_one_attempt(api, same_key):
    barrier = Barrier(2)

    def run(number):
        barrier.wait(timeout=5)
        return checkout(api, "same" if same_key else str(number))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [1, 2]))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    assert len(api[7]["provider_calls"]) == 1
    with Session(api[-1]) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Payment).where(Payment.appointment_id == api[2])
            )
            == 1
        )


def test_keys_conflict_and_scope(api):
    assert checkout(api).status_code == 201
    result = checkout(api, appointment=uuid4())
    assert result.status_code == 409 and result.json()["error"]["code"] == "idempotency_conflict"
    assert checkout(api, subject=api[4]).status_code == 404


def test_foreign_first_request_cannot_block_owner(api):
    assert checkout(api, subject=api[4]).status_code == 404
    assert checkout(api).status_code == 201


@pytest.mark.parametrize(
    "extra",
    [
        {"amount_minor": 1},
        {"tenant_id": str(uuid4())},
        {"return_url": "https://evil.test"},
        {"commission_bps": 0},
    ],
)
def test_rejects_untrusted_fields(api, extra):
    assert checkout(api, extra=extra).status_code == 422
    assert not api[7]["provider_calls"]


@pytest.mark.parametrize("key", ["", "bad key", "x" * 65, "with/slash"])
def test_invalid_keys(api, key):
    assert checkout(api, key=key).status_code == 422


def test_user_authentication_and_roles(api):
    client, user, appointment, *_ = api
    body = {"appointment_id": str(appointment)}
    assert client.post("/consultation-checkouts", json=body).status_code == 401
    assert (
        client.post("/consultation-checkouts", headers=user(token_use="id"), json=body).status_code
        == 401
    )
    assert client.post("/consultation-checkouts", headers=user(), json=body).status_code == 422
    api[7]["role"] = "platform_admin"
    assert checkout(api).status_code == 403


@pytest.mark.parametrize(
    "source,code",
    [
        ("reserve_error", 409),
        ("reserve_error", 503),
        ("profile_error", 409),
        ("profile_error", 503),
    ],
)
def test_sources_fail_closed(api, source, code):
    api[7][source] = code
    assert checkout(api).status_code == code
    assert not api[7]["provider_calls"]


def test_uncertain_create_reuses_persisted_operation(api):
    api[7]["timeout"] = True
    result = checkout(api)
    assert result.status_code == 503
    payment_id = result.json()["error"]["details"][0]["message"]
    api[7]["timeout"] = False
    api[7]["rate"] = 8000
    # A different request key still resumes the same durable provider operation.
    recovered = checkout(api, key="after-restart")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["payment"]["payment_id"] == payment_id
    requests = api[7]["provider_calls"]
    assert requests[0].headers["Idempotency-Key"] == requests[1].headers["Idempotency-Key"]
    assert requests[0].content == requests[1].content
    assert recovered.json()["payment"]["commission_bps"] == 1000
    assert len(api[7]["sessions"]) == 1


def test_definitive_failure_allows_new_attempt(api):
    api[7]["rejected"] = True
    assert checkout(api).status_code == 502
    api[7]["rejected"] = False
    assert checkout(api).status_code == 502
    assert checkout(api, key="retry").status_code == 201


@pytest.mark.parametrize(
    "malformed",
    [
        {"livemode": True},
        {"currency": "usd"},
        {"amount_total": 1},
        {"client_reference_id": "foreign"},
        {"url": "http://checkout.stripe.com/pay"},
        {"url": "https://evil.test/pay"},
    ],
)
def test_provider_context_must_match(api, malformed):
    api[7]["malformed"] = malformed
    assert checkout(api).status_code == 503
    with Session(api[-1]) as session:
        payment = session.scalar(select(Payment).where(Payment.appointment_id == api[2]))
        assert payment.status == "pending" and payment.provider_checkout_id is None


@pytest.mark.parametrize("lost_response,paid", [(False, False), (True, False), (False, True)])
def test_expiry_worker_reconciles_before_marking_failed(api, lost_response, paid):
    api[7]["timeout"] = lost_response
    result = checkout(api)
    assert result.status_code == (503 if lost_response else 201)
    api[7].update(timeout=False, paid=paid)
    with Session(api[-1]) as session, session.begin():
        attempt = session.scalar(
            select(CheckoutAttempt).where(CheckoutAttempt.appointment_id == api[2])
        )
        attempt.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        payment_id = attempt.payment_id
    outcome = expire_due(api[-1], api[0].app.state.provider)
    assert outcome["closed"] >= 1
    with Session(api[-1]) as session:
        payment = session.get(Payment, payment_id)
        assert payment.status == ("pending" if paid else "failed")
        assert payment.provider_checkout_id is not None
    assert expire_due(api[-1], api[0].app.state.provider)["closed"] == 0


def test_success_blocks_new_key_but_original_replays(api):
    original = checkout(api).json()
    with Session(api[-1]) as session, session.begin():
        session.get(Payment, UUID(original["payment"]["payment_id"])).status = "succeeded"
    assert checkout(api).json() == original
    assert checkout(api, "new").json()["error"]["code"] == "already_paid"


def test_internal_payment_read_requires_scoped_service_token(api):
    payment_id = checkout(api).json()["payment"]["payment_id"]
    client = api[0]
    path = "/internal/payments/" + payment_id
    assert client.get(path).status_code == 401
    assert client.get(path, headers=api[1]()).status_code == 401
    settings = client.app.state.settings
    token = service_token(settings.scheduling_secret, "scheduling", "telelink-billing-scheduling")
    assert client.get(path, headers={"Authorization": "Bearer " + token}).status_code == 200


def test_consultation_payment_reader_has_separate_read_only_credentials(api):
    from pydantic import SecretStr

    from tests.helpers import insert, payment_values

    client = api[0]
    payment_id = checkout(api).json()["payment"]["payment_id"]
    secret = SecretStr("v02-billing-consultation-at-least-32-bytes")
    client.app.state.settings.consultation_secret = secret
    client.app.state.settings.fulfilment_secret = SecretStr(
        "v02-fulfilment-secret-at-least-32-bytes"
    )
    token = service_token(secret, "consultation", "telelink-billing-consultation")
    headers = {"Authorization": "Bearer " + token}
    path = "/internal/payments/" + payment_id
    assert client.get(path, headers=headers).status_code == 200
    assert (
        client.post(
            path + "/resolution",
            headers=headers,
            json={
                "resolution": "refund_required",
                "resource_id": str(uuid4()),
                "reason": "quote_expired",
            },
        ).status_code
        == 401
    )
    order, quote = uuid4(), uuid4()
    other = insert(
        api[-1],
        payment_values(
            purpose="medication_delivery", appointment_id=None, order_id=order, quote_id=quote
        ),
    )
    assert client.get("/internal/payments/" + str(other), headers=headers).status_code == 404
    wrong = service_token(secret, "consultation", "telelink-billing-scheduling")
    assert client.get(path, headers={"Authorization": "Bearer " + wrong}).status_code == 401


def test_readiness_requires_checkout_configuration():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_uncertain_operations_are_not_recreated_after_stripe_key_retention(api):
    api[7]["timeout"] = True
    assert checkout(api).status_code == 503
    with Session(api[-1]) as session, session.begin():
        attempt = session.scalar(
            select(CheckoutAttempt).where(CheckoutAttempt.appointment_id == api[2])
        )
        attempt.created_at = datetime.now(timezone.utc) - timedelta(hours=24)
    api[7]["timeout"] = False
    assert checkout(api, "new-key").status_code == 503
    assert len(api[7]["provider_calls"]) == 1


def test_expiry_cannot_regress_concurrent_verified_success(api, monkeypatch):
    original = checkout(api).json()
    payment_id = UUID(original["payment"]["payment_id"])
    with Session(api[-1]) as session, session.begin():
        session.get(CheckoutAttempt, payment_id).hold_expires_at = datetime.now(
            timezone.utc
        ) - timedelta(seconds=1)

    def provider_expire(checkout_id, requested_payment_id):
        assert requested_payment_id == payment_id
        with Session(api[-1]) as session, session.begin():
            session.get(Payment, payment_id).status = "succeeded"
        return {"status": "expired", "payment_status": "unpaid"}

    monkeypatch.setattr(api[0].app.state.provider, "expire", provider_expire)
    assert expire_due(api[-1], api[0].app.state.provider)["closed"] == 1
    with Session(api[-1]) as session:
        assert session.get(Payment, payment_id).status == "succeeded"


def test_unconfigured_clinic_destination_fails_without_provider_call(api):
    api[0].app.state.settings.stripe_destinations = {}
    assert checkout(api).status_code == 503
    assert not api[7]["provider_calls"]
