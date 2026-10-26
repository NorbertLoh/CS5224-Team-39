"""B06 uses explicit C04 fulfilment/Stripe fixtures, with actual PostgreSQL state."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token

from app.integrations.stripe import StripeCheckout
from app.integrations.upstream import CheckoutSources
from app.models import MedicationCheckoutAttempt, Payment, StripeWebhookEvent, event_outbox
from app.services.payments import process_pending
from app.workers.expiry import expire_due
from tests import test_checkout as consultation_tests
from tests.test_payment_processing import receipt as signed_receipt

FULFILMENT = "b06-fulfilment-secret-with-at-least-32-bytes"
authenticated_api = consultation_tests.api


@pytest.fixture
def medication_api(authenticated_api):
    api = authenticated_api
    client, _, _, patient, _, tenant, expires, state, database = api
    with database.begin() as connection:
        connection.execute(text("TRUNCATE billing.event_outbox, billing.stripe_webhook_events"))
    order, quote = uuid4(), uuid4()
    settings = client.app.state.settings
    settings.fulfilment_url = "http://fulfilment.test"
    from pydantic import SecretStr

    settings.fulfilment_secret = SecretStr(FULFILMENT)
    state["reservation"] = {
        "order_id": str(order),
        "quote_id": str(quote),
        "tenant_id": str(tenant),
        "patient_id": str(patient),
        "status": "awaiting_payment",
        "payment_status": "pending",
        "quote_status": "accepted",
        "expires_at": expires.isoformat(),
        "items": [
            {
                "prescription_item_id": str(uuid4()),
                "medication_id": str(uuid4()),
                "quantity": 2,
                "unit_price": money(1000),
                "line_total": money(2000),
            }
        ],
        "medication_subtotal": money(2000),
        "delivery_fee": money(500),
        "total": money(2500),
    }
    state.update(source_status=200, source_code="quote_expired", reservation_calls=[])

    def sources(request):
        fulfilment = request.url.host == "fulfilment.test"
        claims = jwt.decode(
            request.headers["Authorization"].split()[1],
            FULFILMENT if fulfilment else settings.tenant_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer="telelink-service:billing",
            audience=("telelink-fulfilment-billing" if fulfilment else "telelink-tenant-billing"),
        )
        assert claims["sub"] == "billing" and claims["exp"] - claims["iat"] == 60
        if not fulfilment:
            return httpx.Response(
                200,
                json={
                    "tenant_id": str(tenant),
                    "status": "active",
                    "commission_bps": state["rate"],
                },
            )
        assert request.url.path == f"/internal/orders/{order}/checkout-reservation"
        assert request.headers["X-Request-ID"]
        data = json.loads(request.content)
        state["reservation_calls"].append(data)
        if data["patient_id"] != str(patient):
            return httpx.Response(404)
        if state["source_status"] != 200:
            return httpx.Response(
                state["source_status"], json={"error": {"code": state["source_code"]}}
            )
        return httpx.Response(200, json={"payment_id": data["payment_id"]} | state["reservation"])

    client.app.state.sources.close()
    client.app.state.sources = CheckoutSources(settings, transport=httpx.MockTransport(sources))
    yield api, order, quote


def money(amount):
    return {"amount_minor": amount, "currency": "SGD"}


def test_reserved_operation_without_payment_expires_safely_and_is_service_readable(
    medication_api, monkeypatch
):
    from pydantic import SecretStr
    from telelink_common.errors import DomainError

    api, order_id, quote_id = medication_api
    client, database = api[0], api[8]

    def unavailable(*args):
        raise DomainError(503, "unavailable", "Profile unavailable.")

    monkeypatch.setattr(client.app.state.sources, "profile", unavailable)
    assert checkout(medication_api).status_code == 503
    with Session(database) as session:
        attempt = session.scalar(
            select(MedicationCheckoutAttempt).where(MedicationCheckoutAttempt.order_id == order_id)
        )
        payment_id = attempt.payment_id
        assert attempt.quote_expires_at is not None and attempt.reservation is not None
        assert session.get(Payment, payment_id) is None
        attempt.quote_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert expire_due(database, client.app.state.provider)["closed"] == 1
    path = f"/internal/medication-checkouts/{payment_id}"
    assert client.get(path).status_code == 401
    response = client.get(
        path,
        headers={
            "Authorization": "Bearer "
            + service_token(SecretStr(FULFILMENT), "fulfilment", "telelink-billing-fulfilment")
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "payment_id": str(payment_id),
        "order_id": str(order_id),
        "quote_id": str(quote_id),
        "patient_id": str(api[3]),
        "status": "failed",
    }
    assert api[7]["provider_calls"] == []


def checkout(flow, key="medication", subject=None, body=None):
    api, order, quote = flow
    return api[0].post(
        "/medication-checkouts",
        headers=api[1](subject or api[3]) | {"Idempotency-Key": key},
        json=body if body is not None else {"order_id": str(order), "quote_id": str(quote)},
    )


def test_trusted_totals_commission_and_snapshot_replay(medication_api):
    api, order, quote = medication_api
    result = checkout(medication_api)
    assert result.status_code == 201, result.text
    body = result.json()
    payment = body["payment"]
    assert payment["purpose"] == "medication_delivery"
    assert (payment["order_id"], payment["quote_id"], payment["appointment_id"]) == (
        str(order),
        str(quote),
        None,
    )
    assert payment["amount"] == money(2500)
    assert payment["commission_amount"] == money(200)  # Delivery 500 excluded.
    assert payment["clinic_amount"] == money(2300)
    assert body["expires_at"] == api[6].isoformat().replace("+00:00", "Z")
    assert "provider" not in json.dumps(body)
    fields = parse_qs(api[7]["provider_calls"][0].content.decode())
    assert fields["metadata[purpose]"] == ["medication_delivery"]
    assert fields["metadata[order_id]"] == [str(order)]
    assert fields["metadata[quote_id]"] == [str(quote)]
    assert "metadata[appointment_id]" not in fields
    assert fields["payment_intent_data[application_fee_amount]"] == ["200"]
    api[7]["rate"] = 9000
    api[7]["reservation"]["total"] = money(1)
    for key in ("medication", "another"):
        replay = checkout(medication_api, key)
        assert replay.status_code == 200 and replay.json() == body
    assert len(api[7]["provider_calls"]) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_checkout_is_one_provider_operation(medication_api, same_key):
    barrier = Barrier(2)

    def run(number):
        barrier.wait(timeout=5)
        return checkout(medication_api, "same" if same_key else str(number))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [1, 2]))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    assert len(medication_api[0][7]["provider_calls"]) == 1


def test_context_concealment_key_conflicts_and_paid_guard(medication_api):
    api, order, _ = medication_api
    assert checkout(medication_api, subject=api[4]).status_code == 404
    result = checkout(medication_api)
    assert result.status_code == 201
    assert checkout(medication_api, subject=api[4], key="other").status_code == 404
    changed = {"order_id": str(order), "quote_id": str(uuid4())}
    assert checkout(medication_api, body=changed).json()["error"]["code"] == "idempotency_conflict"
    assert (
        checkout(medication_api, key="new", body=changed).json()["error"]["code"]
        == "payment_attempt_pending"
    )
    with Session(api[-1]) as session, session.begin():
        session.get(Payment, UUID(result.json()["payment"]["payment_id"])).status = "succeeded"
    assert checkout(medication_api, key="paid").json()["error"]["code"] == "already_paid"
    assert checkout(medication_api).json() == result.json()


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount_minor", 1),
        ("total", money(1)),
        ("patient_id", str(uuid4())),
        ("tenant_id", str(uuid4())),
        ("delivery_fee", money(0)),
        ("quantity", 1),
        ("provider_checkout_id", "cs_test_injected"),
    ],
)
def test_browser_cannot_supply_trusted_fields(medication_api, field, value):
    _, order, quote = medication_api
    result = checkout(
        medication_api, body={"order_id": str(order), "quote_id": str(quote), field: value}
    )
    assert result.status_code == 422
    assert not medication_api[0][7]["provider_calls"]


@pytest.mark.parametrize("key", ["", "bad key", "x" * 65, "slash/key"])
def test_invalid_idempotency_keys(medication_api, key):
    assert checkout(medication_api, key=key).status_code == 422


def test_authentication_and_current_role_required(medication_api):
    api, order, quote = medication_api
    body = {"order_id": str(order), "quote_id": str(quote)}
    assert api[0].post("/medication-checkouts", json=body).status_code == 401
    assert api[0].post("/medication-checkouts", json=body, headers=api[1]()).status_code == 422
    api[7]["role"] = "platform_admin"
    assert checkout(medication_api).status_code == 403
    api[7]["role"] = None
    assert checkout(medication_api).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("order_id", str(uuid4())),
        ("quote_id", str(uuid4())),
        ("patient_id", str(uuid4())),
        ("payment_id", str(uuid4())),
        ("tenant_id", str(uuid4())),
        ("quote_status", "superseded"),
        ("payment_status", "succeeded"),
        ("status", "cancelled"),
        ("total", money(2499)),
        ("medication_subtotal", money(1999)),
        ("delivery_fee", {"amount_minor": 500, "currency": "USD"}),
        ("expires_at", "2026-10-18T10:00:00"),
        ("items", []),
    ],
)
def test_untrusted_upstream_context_and_totals_fail_closed(medication_api, field, value):
    medication_api[0][7]["reservation"][field] = value
    result = checkout(medication_api)
    assert result.status_code in {502, 503}, result.text
    assert not medication_api[0][7]["provider_calls"]


@pytest.mark.parametrize("change", ["quantity", "line_total", "duplicate", "bool_amount"])
def test_invalid_line_arithmetic_and_duplicate_items(medication_api, change):
    items = medication_api[0][7]["reservation"]["items"]
    if change == "duplicate":
        items.append(copy.deepcopy(items[0]))
    elif change == "bool_amount":
        items[0]["unit_price"]["amount_minor"] = True
    else:
        items[0][change] = 1 if change == "quantity" else money(1)
    assert checkout(medication_api).status_code == 502
    assert not medication_api[0][7]["provider_calls"]


@pytest.mark.parametrize(
    "status,code",
    [
        (409, "quote_superseded"),
        (409, "prescription_not_issued"),
        (409, "already_paid"),
        (404, "not_found"),
        (503, "unavailable"),
    ],
)
def test_upstream_conflicts_and_outages(medication_api, status, code):
    medication_api[0][7].update(source_status=status, source_code=code)
    result = checkout(medication_api)
    assert result.status_code == status
    assert result.json()["error"]["code"] == code
    assert not medication_api[0][7]["provider_calls"]


def test_quote_expiry_equality(medication_api, monkeypatch):
    api = medication_api[0]
    deadline = api[6]
    monkeypatch.setattr("app.services.medication_checkout.now", lambda: deadline)
    result = checkout(medication_api)
    assert result.status_code == 409 and result.json()["error"]["code"] == "quote_expired"
    assert not api[7]["provider_calls"]
    with Session(api[-1]) as session:
        assert session.scalar(select(MedicationCheckoutAttempt)).closed_at is not None


def test_lost_provider_response_reuses_snapshot_and_parameters(medication_api):
    api = medication_api[0]
    api[7]["timeout"] = True
    assert checkout(medication_api).status_code == 503
    api[7].update(timeout=False, rate=9000)
    recovered = checkout(medication_api, key="restarted")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["payment"]["commission_bps"] == 1000
    first, second = api[7]["provider_calls"]
    assert first.content == second.content
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert len(api[7]["sessions"]) == 1


def test_changed_accepted_snapshot_cannot_resume_uncertain_payment(medication_api):
    api = medication_api[0]
    api[7]["timeout"] = True
    assert checkout(medication_api).status_code == 503
    api[7]["timeout"] = False
    api[7]["reservation"].update(delivery_fee=money(600), total=money(2600))
    assert checkout(medication_api).status_code == 503
    assert len(api[7]["provider_calls"]) == 1


@pytest.mark.parametrize("lost,paid", [(False, False), (True, False), (False, True)])
def test_expiry_worker_reconciles_medication_attempt(medication_api, lost, paid):
    api = medication_api[0]
    api[7]["timeout"] = lost
    assert checkout(medication_api).status_code == (503 if lost else 201)
    api[7].update(timeout=False, paid=paid)
    with Session(api[-1]) as session, session.begin():
        attempt = session.scalar(select(MedicationCheckoutAttempt))
        payment_id = attempt.payment_id
        attempt.quote_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert expire_due(api[-1], api[0].app.state.provider)["closed"] == 1
    with Session(api[-1]) as session:
        payment = session.get(Payment, payment_id)
        assert payment.status == ("pending" if paid else "failed")
        assert payment.provider_checkout_id is not None
    assert expire_due(api[-1], api[0].app.state.provider)["closed"] == 0


def paid_provider(flow):
    api = flow[0]
    response = checkout(flow)
    assert response.status_code == 201, response.text
    payment_id = UUID(response.json()["payment"]["payment_id"])
    with Session(api[-1]) as session:
        payment = session.get(Payment, payment_id)
        fields = session.get(MedicationCheckoutAttempt, payment_id).provider_fields
        metadata = {
            key[9:-1]: value for key, value in fields.items() if key.startswith("metadata[")
        }
        state = {
            "checkout": {
                "id": payment.provider_checkout_id,
                "object": "checkout.session",
                "livemode": False,
                "mode": "payment",
                "status": "complete",
                "payment_status": "paid",
                "amount_total": payment.amount_minor,
                "currency": "sgd",
                "client_reference_id": str(payment_id),
                "metadata": metadata,
                "payment_intent": "pi_B06",
            },
            "intent": {
                "id": "pi_B06",
                "object": "payment_intent",
                "livemode": False,
                "status": "succeeded",
                "amount": payment.amount_minor,
                "amount_received": payment.amount_minor,
                "currency": "sgd",
                "metadata": metadata,
                "application_fee_amount": payment.commission_amount_minor,
                "transfer_data": {"destination": "acct_synthetic"},
            },
        }

    def transport(request):
        assert request.method == "GET"
        return httpx.Response(
            200, json=state["checkout" if "checkout/sessions" in request.url.path else "intent"]
        )

    provider = StripeCheckout(api[0].app.state.settings, transport=httpx.MockTransport(transport))
    return api[-1], provider, {"payment_id": payment_id}, state


@pytest.mark.parametrize("late", [False, True])
def test_signed_medication_success_commits_one_outbox_fact(medication_api, late):
    flow = paid_provider(medication_api)
    database, provider, values, _ = flow
    try:
        if late:
            with Session(database) as session, session.begin():
                attempt = session.get(MedicationCheckoutAttempt, values["payment_id"])
                attempt.quote_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        signed_receipt(flow, via_http=True)
        signed_receipt(flow, "payment_intent.succeeded")
        assert process_pending(database, provider)["processed"] == 2
        with Session(database) as session:
            payment = session.get(Payment, values["payment_id"])
            assert payment.status == "succeeded"
            assert payment.resolution == ("refund_required" if late else "none")
            (row,) = session.execute(select(event_outbox)).mappings().all()
            assert row["detail_type"] == "medication_payment_succeeded.v1"
            assert json.loads(row["detail"])["data"] == {
                "payment_id": str(payment.payment_id),
                "order_id": str(medication_api[1]),
                "amount": money(2500),
            }
    finally:
        provider.close()


@pytest.mark.parametrize("field", ["order_id", "quote_id", "tenant_id", "purpose"])
def test_webhook_reconciliation_rejects_wrong_medication_metadata(medication_api, field):
    flow = paid_provider(medication_api)
    try:
        flow[3]["intent"]["metadata"][field] = str(uuid4())
        signed_receipt(flow)
        assert process_pending(flow[0], flow[1])["rejected"] == 1
        with Session(flow[0]) as session:
            assert session.get(Payment, flow[2]["payment_id"]).status == "pending"
            assert session.execute(select(event_outbox)).first() is None
    finally:
        flow[1].close()


def test_atomic_medication_success_rolls_back_and_retries(medication_api):
    flow = paid_provider(medication_api)
    event_id = signed_receipt(flow)

    def crash(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO billing.event_outbox"):
            raise RuntimeError("synthetic crash")

    event.listen(flow[0], "before_cursor_execute", crash)
    try:
        with pytest.raises(RuntimeError, match="synthetic crash"):
            process_pending(flow[0], flow[1])
    finally:
        event.remove(flow[0], "before_cursor_execute", crash)
    try:
        with Session(flow[0]) as session:
            assert session.get(Payment, flow[2]["payment_id"]).status == "pending"
            assert session.get(StripeWebhookEvent, event_id).status == "pending"
            assert session.execute(select(event_outbox)).first() is None
        assert process_pending(flow[0], flow[1])["processed"] == 1
    finally:
        flow[1].close()


def test_fulfilment_can_read_only_medication_payment_context(medication_api):
    api = medication_api[0]
    payment_id = checkout(medication_api).json()["payment"]["payment_id"]
    path = "/internal/payments/" + payment_id
    settings = api[0].app.state.settings
    token = service_token(settings.fulfilment_secret, "fulfilment", "telelink-billing-fulfilment")
    assert api[0].get(path, headers={"Authorization": "Bearer " + token}).status_code == 200
    token = service_token(settings.scheduling_secret, "scheduling", "telelink-billing-scheduling")
    assert api[0].get(path, headers={"Authorization": "Bearer " + token}).status_code == 404
    assert api[0].get(path, headers=api[1]()).status_code == 401


def test_fulfilment_resolution_is_scoped_durable_and_idempotent(medication_api):
    api, order, _ = medication_api
    payment_id = checkout(medication_api).json()["payment"]["payment_id"]
    path = "/internal/payments/" + payment_id + "/resolution"
    settings = api[0].app.state.settings
    token = service_token(settings.fulfilment_secret, "fulfilment", "telelink-billing-fulfilment")
    headers = {"Authorization": "Bearer " + token}
    body = {"resource_id": str(order), "resolution": "refund_required", "reason": "order_cancelled"}
    assert api[0].post(path, json=body, headers=api[1]()).status_code == 401
    assert api[0].post(path, json=body, headers=headers).status_code == 409
    with Session(api[-1]) as session, session.begin():
        session.get(Payment, UUID(payment_id)).status = "succeeded"
    assert (
        api[0].post(path, json=body | {"resource_id": str(uuid4())}, headers=headers).status_code
        == 404
    )
    assert (
        api[0].post(path, json=body | {"reason": "untrusted"}, headers=headers).status_code == 422
    )
    original = api[0].post(path, json=body, headers=headers)
    assert original.status_code == 200 and original.json()["resolution"] == "refund_required"
    assert api[0].post(path, json=body, headers=headers).json() == original.json()
    with Session(api[-1]) as session:
        attempt = session.get(MedicationCheckoutAttempt, UUID(payment_id))
        assert attempt.resolution_reason == "order_cancelled"
        assert attempt.resolution_requested_at is not None
    # No refund or new Checkout is submitted by operational resolution.
    assert len(api[7]["provider_calls"]) == 1


def test_accepted_reservation_timeout_retries_same_payment_identity(medication_api):
    api = medication_api[0]
    api[7]["source_status"] = 503
    assert checkout(medication_api).status_code == 503
    first = api[7]["reservation_calls"][0]
    api[7]["source_status"] = 200
    assert checkout(medication_api, key="recovered").status_code == 200
    assert api[7]["reservation_calls"][1] == first


def test_provider_rejection_never_retries_same_operation(medication_api):
    api = medication_api[0]
    api[7]["rejected"] = True
    assert checkout(medication_api).status_code == 502
    api[7]["rejected"] = False
    assert checkout(medication_api).status_code == 502
    assert len(api[7]["provider_calls"]) == 1


def test_expiry_cannot_regress_concurrent_medication_success(medication_api, monkeypatch):
    api = medication_api[0]
    payment_id = UUID(checkout(medication_api).json()["payment"]["payment_id"])
    with Session(api[-1]) as session, session.begin():
        session.get(MedicationCheckoutAttempt, payment_id).quote_expires_at = datetime.now(
            timezone.utc
        )

    def provider_expire(checkout_id, requested_payment_id):
        assert requested_payment_id == payment_id
        with Session(api[-1]) as session, session.begin():
            session.get(Payment, payment_id).status = "succeeded"
        return {"status": "expired", "payment_status": "unpaid"}

    monkeypatch.setattr(api[0].app.state.provider, "expire", provider_expire)
    assert expire_due(api[-1], api[0].app.state.provider)["closed"] == 1
    with Session(api[-1]) as session:
        assert session.get(Payment, payment_id).status == "succeeded"


def test_uncertain_operation_not_recreated_after_key_retention(medication_api):
    api = medication_api[0]
    api[7]["timeout"] = True
    assert checkout(medication_api).status_code == 503
    with Session(api[-1]) as session, session.begin():
        session.scalar(select(MedicationCheckoutAttempt)).created_at = datetime.now(
            timezone.utc
        ) - timedelta(hours=24)
    api[7]["timeout"] = False
    assert checkout(medication_api, key="new").status_code == 503
    assert len(api[7]["provider_calls"]) == 1
