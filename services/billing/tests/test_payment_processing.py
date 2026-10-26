import copy
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.outbox import publish_pending

from app.checkout import checkout_lock
from app.main import create_app
from app.models import CheckoutAttempt, Payment, StripeWebhookEvent, event_outbox
from app.payments import process_pending
from app.provider import StripeCheckout
from app.settings import Settings
from app.webhooks import persist_receipt, verify_event
from tests.helpers import insert, payment_values, read

SECRET = "whsec_B04_synthetic"


@pytest.fixture
def flow(database):
    with database.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE billing.event_outbox, billing.stripe_webhook_events, "
                "billing.checkout_keys, billing.checkout_attempts, billing.payments, "
                "billing.medication_checkout_keys, billing.medication_checkout_attempts, "
                "billing.refund_attempts"
            )
        )
    values = payment_values(provider_checkout_id="cs_test_" + uuid4().hex)
    payment_id = insert(database, values)
    intent_id = "pi_" + uuid4().hex
    metadata = {
        name: str(values[name])
        for name in ("payment_id", "appointment_id", "tenant_id", "patient_id", "purpose")
    }
    state = {
        "checkout": {
            "id": values["provider_checkout_id"],
            "object": "checkout.session",
            "livemode": False,
            "mode": "payment",
            "status": "complete",
            "payment_status": "paid",
            "amount_total": values["amount_minor"],
            "currency": "sgd",
            "client_reference_id": str(payment_id),
            "metadata": metadata,
            "payment_intent": intent_id,
        },
        "intent": {
            "id": intent_id,
            "object": "payment_intent",
            "livemode": False,
            "status": "succeeded",
            "amount": values["amount_minor"],
            "amount_received": values["amount_minor"],
            "currency": "sgd",
            "metadata": metadata,
            "application_fee_amount": values["commission_amount_minor"],
            "transfer_data": {"destination": "acct_original"},
        },
        "calls": [],
        "unavailable": False,
    }

    def transport(request):
        assert request.method == "GET"  # B04 must never create a second charge.
        assert request.headers["Authorization"] == "Bearer sk_test_synthetic"
        assert request.headers["Stripe-Version"] == "2024-06-20"
        state["calls"].append(str(request.url))
        if state["unavailable"]:
            raise httpx.ReadTimeout("PRIVATE PROVIDER ERROR")
        if request.url.path == "/v1/checkout/sessions/" + values["provider_checkout_id"]:
            return httpx.Response(200, json=state["checkout"])
        if request.url.path == "/v1/payment_intents/" + intent_id:
            return httpx.Response(200, json=state["intent"])
        return httpx.Response(404)

    provider = StripeCheckout(
        Settings(_env_file=None, environment="test", stripe_secret_key="sk_test_synthetic"),
        transport=httpx.MockTransport(transport),
    )
    with Session(database) as session, session.begin():
        payment = session.get(Payment, payment_id)
        session.add(
            CheckoutAttempt(
                payment_id=payment_id,
                appointment_id=payment.appointment_id,
                patient_id=payment.patient_id,
                hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=8),
                provider_fields=provider.fields(payment, "acct_original"),
            )
        )
    yield database, provider, values, state
    provider.close()


def receipt(flow, event_type="checkout.session.completed", *, changes=None, via_http=False):
    database, _, _, state = flow
    obj = copy.deepcopy(state["checkout" if event_type.startswith("checkout.") else "intent"])
    value = {
        "id": "evt_" + uuid4().hex,
        "object": "event",
        "type": event_type,
        "livemode": False,
        "created": int(time.time()),
        "data": {"object": obj},
    }
    value.update(changes or {})
    body = json.dumps(value).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    if via_http:
        app = create_app(Settings(_env_file=None, environment="test", stripe_webhook_secret=SECRET))
        with TestClient(app) as client:
            app.state.database_engine = database
            assert (
                client.post(
                    "/webhooks/stripe", content=body, headers={"Stripe-Signature": signature}
                ).status_code
                == 200
            )
            app.state.database_engine = None
    else:
        persist_receipt(database, verify_event(body, signature, SECRET))
    return value["id"]


def process(flow, **kwargs):
    return process_pending(flow[0], flow[1], **kwargs)


def stored(flow, event_id):
    with Session(flow[0]) as session:
        row = session.get(StripeWebhookEvent, event_id)
        session.expunge(row)
        return row


def outbox(flow):
    with flow[0].connect() as connection:
        return connection.execute(select(event_outbox)).mappings().all()


def test_signed_receipt_commits_payment_and_c05_success(flow):
    event_id = receipt(flow, via_http=True)
    assert process(flow)["processed"] == 1
    payment = read(flow[0], flow[2]["payment_id"])
    assert payment["status"] == "succeeded"
    assert payment["provider_payment_id"] == flow[3]["intent"]["id"]
    assert stored(flow, event_id).processed_at is not None
    (row,) = outbox(flow)
    detail = json.loads(row["detail"])
    assert row["source"] == "telelink.billing"
    assert row["detail_type"] == "consultation_payment_succeeded.v1"
    assert detail["tenant_id"] == str(flow[2]["tenant_id"])
    assert detail["correlation_id"] == str(flow[2]["payment_id"])
    assert detail["data"] == {
        "payment_id": str(flow[2]["payment_id"]),
        "appointment_id": str(flow[2]["appointment_id"]),
        "amount": {"amount_minor": flow[2]["amount_minor"], "currency": "SGD"},
    }
    assert row["published_at"] is None


def test_distinct_success_events_have_one_business_effect(flow):
    receipt(flow)
    receipt(flow, "payment_intent.succeeded")
    receipt(flow, "checkout.session.async_payment_succeeded")
    assert process(flow)["processed"] == 3
    assert len(outbox(flow)) == 1
    assert process(flow)["processed"] == 0


def test_concurrent_workers_have_one_success(flow):
    for _ in range(6):
        receipt(flow)
    barrier = Barrier(4)

    def worker(_):
        barrier.wait(timeout=10)
        return process(flow)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))
    assert sum(r["processed"] for r in results) >= 1
    process(flow, now=datetime.now(timezone.utc) + timedelta(minutes=6))
    assert len(outbox(flow)) == 1
    assert read(flow[0], flow[2]["payment_id"])["status"] == "succeeded"


@pytest.mark.parametrize(
    "status", ["pending", "failed", "succeeded", "refund_pending", "refunded", "refund_failed"]
)
def test_success_never_regresses_refund_state_and_late_failure(flow, status):
    with flow[0].begin() as connection:
        connection.execute(
            text("UPDATE billing.payments SET status=:status WHERE payment_id=:id"),
            {"status": status, "id": flow[2]["payment_id"]},
        )
    receipt(flow)
    assert process(flow)["processed"] == 1
    expected = "succeeded" if status in {"pending", "failed"} else status
    assert read(flow[0], flow[2]["payment_id"])["status"] == expected
    assert len(outbox(flow)) == (1 if status in {"pending", "failed"} else 0)
    # A delayed failure whose provider now reports success never erases success.
    receipt(flow, "payment_intent.payment_failed")
    process(flow)
    assert read(flow[0], flow[2]["payment_id"])["status"] == expected


def test_late_success_is_published_for_scheduling_recovery(flow):
    with Session(flow[0]) as session, session.begin():
        payment = session.get(Payment, flow[2]["payment_id"])
        attempt = session.get(CheckoutAttempt, payment.payment_id)
        payment.status = "failed"
        attempt.hold_expires_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        attempt.closed_at = attempt.hold_expires_at
    receipt(flow)
    assert process(flow)["processed"] == 1
    assert read(flow[0], flow[2]["payment_id"])["status"] == "succeeded"
    assert len(outbox(flow)) == 1


def test_expired_unpaid_session_is_terminal_but_card_decline_is_not(flow):
    state = flow[3]
    state["checkout"].update(status="open", payment_status="unpaid")
    state["intent"].update(status="requires_payment_method", amount_received=0)
    receipt(flow, "payment_intent.payment_failed")
    assert process(flow)["processed"] == 1
    assert read(flow[0], flow[2]["payment_id"])["status"] == "pending"
    state["checkout"]["status"] = "expired"
    receipt(flow, "checkout.session.expired")
    assert process(flow)["processed"] == 1
    assert read(flow[0], flow[2]["payment_id"])["status"] == "failed"
    assert outbox(flow) == []


def test_async_failure_is_terminal(flow):
    flow[3]["checkout"]["payment_status"] = "unpaid"
    flow[3]["intent"].update(status="requires_payment_method", amount_received=0)
    receipt(flow, "checkout.session.async_payment_failed")
    process(flow)
    assert read(flow[0], flow[2]["payment_id"])["status"] == "failed"
    assert outbox(flow) == []


@pytest.mark.parametrize(
    ("part", "field", "value"),
    [
        ("checkout", "amount_total", 1),
        ("checkout", "currency", "usd"),
        ("checkout", "client_reference_id", str(uuid4())),
        ("checkout", "metadata", {}),
        ("checkout", "mode", "subscription"),
        ("checkout", "object", "payment_intent"),
        ("intent", "amount", 1),
        ("intent", "currency", "usd"),
        ("intent", "metadata", {}),
        ("intent", "amount_received", 1),
        ("intent", "transfer_data", {"destination": "acct_wrong"}),
        ("intent", "transfer_data", {"destination": "acct_original", "amount": 1}),
        ("intent", "application_fee_amount", 0),
    ],
)
def test_provider_context_mismatch_is_rejected_without_partial_effect(flow, part, field, value):
    event_id = receipt(flow)
    flow[3][part][field] = value
    assert process(flow)["rejected"] == 1
    assert stored(flow, event_id).status == "rejected"
    assert read(flow[0], flow[2]["payment_id"])["status"] == "pending"
    assert read(flow[0], flow[2]["payment_id"])["provider_payment_id"] is None
    assert outbox(flow) == []


def test_wrong_account_is_rejected(flow):
    event_id = receipt(flow, changes={"account": "acct_connected"})
    assert process(flow)["rejected"] == 1
    assert stored(flow, event_id).last_error == "account_mismatch"
    assert flow[3]["calls"] == []


def test_duplicate_intent_binding_is_rejected_atomically(flow):
    insert(flow[0], payment_values(provider_payment_id=flow[3]["intent"]["id"]))
    event_id = receipt(flow)
    assert process(flow)["rejected"] == 1
    assert stored(flow, event_id).last_error == "payment_integrity_conflict"
    assert read(flow[0], flow[2]["payment_id"])["status"] == "pending"
    assert outbox(flow) == []


def test_receipt_with_wrong_object_id_is_rejected(flow):
    obj = dict(flow[3]["checkout"], id="cs_test_wrong")
    event_id = receipt(flow, changes={"data": {"object": obj}})
    assert process(flow)["rejected"] == 1
    assert stored(flow, event_id).last_error == "checkout_id_mismatch"
    assert outbox(flow) == []


def test_processing_and_missing_linkage_retry_until_verified(flow):
    flow[3]["checkout"]["payment_status"] = "unpaid"
    flow[3]["intent"].update(status="processing", amount_received=0)
    event_id = receipt(flow)
    assert process(flow)["deferred"] == 1
    assert stored(flow, event_id).last_error == "provider_processing"
    flow[3]["checkout"]["payment_status"] = "paid"
    flow[3]["intent"].update(status="succeeded", amount_received=flow[2]["amount_minor"])
    assert process(flow, now=stored(flow, event_id).next_attempt_at)["processed"] == 1
    assert len(outbox(flow)) == 1


def test_timeout_defers_and_retries_original_receipt(flow):
    event_id = receipt(flow)
    flow[3]["unavailable"] = True
    assert process(flow)["deferred"] == 1
    row = stored(flow, event_id)
    assert row.status == "pending" and row.attempts == 1
    assert row.last_error == "provider_unavailable"
    assert outbox(flow) == []
    flow[3]["unavailable"] = False
    assert process(flow)["processed"] == 0
    assert process(flow, now=row.next_attempt_at + timedelta(seconds=1))["processed"] == 1
    assert len(outbox(flow)) == 1


def test_receipt_waits_for_inflight_checkout_and_missing_session_link(flow):
    event_id = receipt(flow)
    with checkout_lock(flow[0], flow[2]["appointment_id"]):
        assert process(flow)["deferred"] == 1
    assert stored(flow, event_id).last_error == "checkout_busy"
    with flow[0].begin() as connection:
        connection.execute(text("UPDATE billing.payments SET provider_checkout_id=NULL"))
    later = stored(flow, event_id).next_attempt_at + timedelta(seconds=1)
    assert process(flow, now=later)["deferred"] == 1
    assert stored(flow, event_id).last_error == "checkout_linkage_pending"
    assert flow[3]["calls"] == []


@pytest.mark.parametrize("stage", ["staging", "commit"])
def test_crash_rolls_back_receipt_payment_and_outbox(flow, monkeypatch, stage):
    import app.payments as payments

    event_id = receipt(flow)
    original = payments.add_event

    def crash_after_staging(*args):
        original(*args)
        raise RuntimeError("synthetic crash")

    def crash_before_commit(session):
        if not session.in_nested_transaction():
            raise RuntimeError("synthetic crash")

    if stage == "staging":
        monkeypatch.setattr(payments, "add_event", crash_after_staging)
    else:
        event.listen(Session, "before_commit", crash_before_commit)
    try:
        with pytest.raises(RuntimeError, match="synthetic crash"):
            process(flow)
    finally:
        if stage == "commit":
            event.remove(Session, "before_commit", crash_before_commit)
        monkeypatch.setattr(payments, "add_event", original)
    assert stored(flow, event_id).status == "pending"
    assert read(flow[0], flow[2]["payment_id"])["status"] == "pending"
    assert outbox(flow) == []
    assert process(flow)["processed"] == 1
    assert len(outbox(flow)) == 1


def test_publish_failure_retries_same_stored_event_without_reverting_payment(flow):
    receipt(flow)
    process(flow)

    class EventBridge:
        def __init__(self):
            self.entries = []

        def put_events(self, *, Entries):
            self.entries.append(Entries)
            return {
                "Entries": [
                    {"ErrorCode": "ThrottlingException"}
                    if len(self.entries) == 1
                    else {"EventId": "accepted"}
                ]
            }

    client = EventBridge()
    sessions = sessionmaker(flow[0])
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert publish_pending(sessions, event_outbox, client, "telelink-local", now=now).failed == 1
    assert read(flow[0], flow[2]["payment_id"])["status"] == "succeeded"
    (row,) = outbox(flow)
    assert row["published_at"] is None and row["attempts"] == 1
    assert (
        publish_pending(
            sessions, event_outbox, client, "telelink-local", now=now + timedelta(seconds=6)
        ).published
        == 1
    )
    assert client.entries[0] == client.entries[1]
    assert (
        publish_pending(
            sessions, event_outbox, client, "telelink-local", now=now + timedelta(seconds=7)
        ).published
        == 0
    )
