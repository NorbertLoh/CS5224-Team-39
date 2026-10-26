import hashlib
import hmac
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.webhooks import MAX_BODY_BYTES
from app.main import create_app
from app.models import Payment, StripeWebhookEvent
from app.settings import Settings
from tests.helpers import insert, payment_values

SECRET = "whsec_B03_synthetic_only"
PATH = "/webhooks/stripe"


def snapshot(**changes):
    return {
        "id": "evt_" + uuid4().hex,
        "object": "event",
        "livemode": False,
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "api_version": "2024-06-20",
        "data": {
            "object": {
                "id": "cs_test_synthetic",
                "object": "checkout.session",
                "amount_total": 5000,
                "currency": "sgd",
                "payment_status": "paid",
                "payment_intent": "pi_synthetic",
                "metadata": {"payment_id": str(uuid4()), "private_note": "DO NOT STORE"},
                "customer_details": {"email": "PRIVATE EMAIL"},
            }
        },
        **changes,
    }


def signed(body, *, timestamp=None, secret=SECRET):
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture
def client():
    app = create_app(Settings(_env_file=None, environment="test", stripe_webhook_secret=SECRET))
    with TestClient(app) as client:
        # Validation tests never reach storage.
        app.state.database_engine = object()
        yield client
        app.state.database_engine = None


def send(client, event=None, *, body=None, signature=None):
    if body is None:
        body = json.dumps(snapshot() if event is None else event, indent=2).encode()
    return client.post(PATH, content=body, headers={"Stripe-Signature": signature or signed(body)})


@pytest.mark.parametrize(
    "case", ["missing", "duplicate", "wrong", "tamper", "old", "future", "malformed", "noninteger"]
)
def test_bad_signature_rejected_before_storage(client, case, caplog):
    body = json.dumps(snapshot()).encode()
    signature = signed(body)
    if case == "missing":
        response = client.post(PATH, content=body)
    elif case == "duplicate":
        response = client.post(PATH, content=body, headers=[("Stripe-Signature", signature)] * 2)
    else:
        if case == "wrong":
            signature = signed(body, secret="wrong-secret")
        elif case == "tamper":
            body += b" "
        elif case in {"old", "future"}:
            signature = signed(body, timestamp=int(time.time()) + (-360 if case == "old" else 360))
        elif case == "malformed":
            signature = "invalid"
        elif case == "noninteger":
            signature = "t=abc,v1=abc"
        response = send(client, body=body, signature=signature)
    assert response.status_code == 400
    assert SECRET not in response.text + caplog.text
    assert body.decode() not in response.text + caplog.text


@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b"true", b"\xff"])
def test_signed_invalid_json_shapes(client, body):
    assert send(client, body=body).status_code == 400


@pytest.mark.parametrize(
    "changes",
    [
        {"livemode": True},
        {"livemode": None},
        {"id": "invalid"},
        {"id": 123},
        {"type": None},
        {"created": True},
        {"created": -1},
        {"data": []},
        {"data": {"object": []}},
        {"data": {"object": {"id": "cs_test_x"}}},
        {"account": {}},
        {"api_version": []},
    ],
)
def test_signed_invalid_event_rejected(client, changes):
    assert send(client, snapshot(**changes)).status_code == 400


def test_size_limit_checks_actual_chunks(client):
    assert send(client, body=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413


def test_unconfigured_endpoint_fails_closed(client):
    client.app.state.settings.stripe_webhook_secret = None
    assert send(client).status_code == 503


def test_database_failure_is_retryable(client):
    class BrokenEngine:
        def begin(self):
            raise OperationalError("private sql", {}, Exception("private database error"))

    client.app.state.database_engine = BrokenEngine()
    response = send(client)
    assert response.status_code == 503
    assert "private" not in response.text
    assert response.json()["error"]["code"] == "unavailable"


def test_commit_failure_is_retryable_and_replay_can_insert(client, database):
    from contextlib import contextmanager

    event = snapshot()

    class CommitFailure:
        @contextmanager
        def begin(self):
            with database.connect() as connection, connection.begin():
                yield connection
                raise OperationalError("commit", {}, Exception("synthetic failure"))

    client.app.state.database_engine = CommitFailure()
    assert send(client, event).status_code == 503
    with Session(database) as session:
        assert session.get(StripeWebhookEvent, event["id"]) is None
    client.app.state.database_engine = database
    assert send(client, event).status_code == 200
    client.app.state.database_engine = None


def test_durable_receipt_and_replay_preserve_first_projection(client, database):
    event = snapshot()
    client.app.state.database_engine = database
    response = send(client, event)
    assert response.status_code == 200 and response.json() == {"received": True}
    assert response.headers["cache-control"] == "no-store"
    event["data"]["object"]["amount_total"] = 9999
    assert send(client, event).status_code == 200
    with Session(database) as session:
        row = session.get(StripeWebhookEvent, event["id"])
        assert row.status == "pending"
        assert row.object_data["amount_total"] == 5000
        assert row.object_data["payment_intent"] == "pi_synthetic"
        assert set(row.object_data["metadata"]) == {"payment_id"}
        assert "PRIVATE" not in json.dumps(row.object_data)
        assert row.received_at.utcoffset().total_seconds() == 0
    # A fresh API process sees the same durable receipt.
    with TestClient(
        create_app(Settings(_env_file=None, environment="test", stripe_webhook_secret=SECRET))
    ) as other:
        other.app.state.database_engine = database
        assert send(other, event).status_code == 200
        other.app.state.database_engine = None
    client.app.state.database_engine = None


def test_concurrent_replay_has_one_receipt(client, database):
    event = snapshot()
    barrier = Barrier(6)
    client.app.state.database_engine = database

    def deliver(_):
        barrier.wait(timeout=10)
        return send(client, event).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(deliver, range(6))) == [200] * 6
    with Session(database) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(StripeWebhookEvent)
                .where(StripeWebhookEvent.event_id == event["id"])
            )
            == 1
        )
    client.app.state.database_engine = None


def test_unknown_event_is_recorded_as_ignored(client, database):
    event = snapshot(type="customer.created")
    client.app.state.database_engine = database
    assert send(client, event).status_code == 200
    with Session(database) as session:
        assert session.get(StripeWebhookEvent, event["id"]).status == "ignored"
    client.app.state.database_engine = None


def test_rotating_v1_signature_and_chunked_body(client, database):
    client.app.state.database_engine = database
    body = json.dumps(snapshot()).encode()
    signature = signed(body).replace(",v1=", ",v1=old_signature,v1=")
    response = client.post(
        PATH,
        content=iter([body[:50], body[50:]]),
        headers={"Stripe-Signature": signature},
    )
    assert response.status_code == 200
    client.app.state.database_engine = None


def test_payment_success_receipt_does_not_change_payment(client, database):
    values = payment_values()
    payment_id = insert(database, values)
    event = snapshot()
    event["data"]["object"]["metadata"]["payment_id"] = str(payment_id)
    client.app.state.database_engine = database
    assert send(client, event).status_code == 200
    with Session(database) as session:
        assert session.get(Payment, payment_id).status == "pending"
        assert session.get(StripeWebhookEvent, event["id"]).status == "pending"
    client.app.state.database_engine = None


def test_secret_is_validated_and_redacted():
    with pytest.raises(ValueError):
        Settings(_env_file=None, stripe_webhook_secret="sk_test_not_a_signing_secret")
    assert SECRET not in repr(Settings(_env_file=None, stripe_webhook_secret=SECRET))


@pytest.mark.parametrize("old_first", [True, False])
def test_utf8_raw_bytes_and_rotating_signatures(client, monkeypatch, old_first):
    receipts = []
    monkeypatch.setattr(
        "app.api.webhooks.persist_receipt", lambda engine, values: receipts.append(values)
    )
    event = snapshot()
    event["data"]["object"]["description"] = "café"
    body = json.dumps(event, ensure_ascii=False, indent=2).encode()
    signature = signed(body)
    signature = (
        signature.replace(",v1=", ",v1=old_signature,v1=")
        if old_first
        else signature + ",v1=old_signature"
    )
    assert send(client, body=body, signature=signature).status_code == 200
    assert len(receipts) == 1
    assert receipts[0]["event_id"] == event["id"]
    assert "description" not in receipts[0]["object_data"]
    # Re-encoding equivalent JSON must not authenticate using the original signature.
    changed = json.dumps(json.loads(body)).encode()
    assert changed != body
    assert send(client, body=changed, signature=signature).status_code == 400
    assert len(receipts) == 1


def test_loopback_http_signature_boundary(monkeypatch):
    """Retain X04 socket coverage against the real route; storage is an explicit spy."""
    receipts = []
    monkeypatch.setattr(
        "app.api.webhooks.persist_receipt", lambda engine, values: receipts.append(values)
    )
    app = create_app(Settings(_env_file=None, environment="test", stripe_webhook_secret=SECRET))
    event = snapshot()
    event["data"]["object"]["description"] = "café"
    body = json.dumps(event, ensure_ascii=False).encode()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            app.state.database_engine = object()
            with httpx.Client(timeout=5, trust_env=False) as transport:
                for payload, signature, expected in (
                    (body, signed(body), 200),
                    (body + b"\n", signed(body), 400),
                    (body, signed(body, timestamp=int(time.time()) - 601), 400),
                ):
                    response = transport.post(
                        f"http://127.0.0.1:{port}{PATH}",
                        content=payload,
                        headers={"Stripe-Signature": signature},
                    )
                    assert response.status_code == expected
                    if expected == 200:
                        assert response.json() == {"received": True}
            assert len(receipts) == 1
            assert receipts[0]["event_id"] == event["id"]
        finally:
            app.state.database_engine = None
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()
