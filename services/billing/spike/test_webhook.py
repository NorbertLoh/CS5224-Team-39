"""HTTP boundary tests use synthetic HMACs, never a real endpoint secret."""

import hashlib
import hmac
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from webhook import DEMO_SECRET, MAX_BODY_BYTES, create_app

BODY = (
    b'{"id":"evt_x04_sample","object":"event","type":"payment_intent.succeeded",'
    b'"livemode":false,"data":{"object":{"id":"pi_sample","label":"caf\xc3\xa9"}}}'
)


def signature(body=BODY, secret=DEMO_SECRET, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


@pytest.fixture
def client():
    with TestClient(create_app(DEMO_SECRET)) as client:
        yield client


def post(client, body=BODY, header=None):
    return client.post(
        "/stripe/webhook",
        content=body,
        headers={
            "Stripe-Signature": signature() if header is None else header,
            "Content-Type": "application/json",
        },
    )


def test_raw_utf8_sample_callback(client):
    response = post(client)
    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "event_id": "evt_x04_sample",
        "mode": "signature-spike",
        "payment_processed": False,
    }


@pytest.mark.parametrize(
    "header",
    ["", "nonsense", "t=abc,v1=123", "t=1,v0=123", "t=1,v1=123", "v1=123", "t=1", "t=1,v1="],
)
def test_bad_signature_headers(client, header):
    assert post(client, header=header).status_code == 400


def test_missing_and_duplicate_header(client):
    assert client.post("/stripe/webhook", content=BODY).status_code == 400
    response = client.post(
        "/stripe/webhook",
        content=BODY,
        headers=[("Stripe-Signature", signature()), ("Stripe-Signature", signature())],
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        BODY + b"\n",
        BODY.replace(b"pi_sample", b"pi_changed"),
        json.dumps(json.loads(BODY)).encode(),
    ],
)
def test_changed_bytes_including_json_reserialization_rejected(client, body):
    assert body != BODY
    assert post(client, body=body).status_code == 400


def test_wrong_secret_and_old_or_future_timestamp(client):
    headers = [
        signature(secret="whsec_other"),
        signature(timestamp=int(time.time()) - 601),
        signature(timestamp=int(time.time()) + 601),
    ]
    for header in headers:
        response = post(client, header=header)
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid webhook"}
        assert DEMO_SECRET not in response.text
        assert BODY.decode() not in response.text


def test_multiple_v1_signatures_support_secret_rotation(client):
    assert post(client, header=signature() + ",v1=incorrect").status_code == 200
    assert post(client, header=signature().replace(",v1=", ",v1=incorrect,v1=")).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"\xff",
        b"[]",
        b"null",
        b"{}",
        BODY.replace(b'"livemode":false', b'"livemode":true'),
    ],
)
def test_signed_malformed_or_live_payloads(client, body):
    assert post(client, body=body, header=signature(body)).status_code == 400


def test_size_limit_and_route_boundary(client):
    assert post(client, body=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
    assert client.get("/stripe/webhook").status_code == 405
    assert client.post("/other", content=BODY).status_code == 404


@pytest.mark.parametrize("secret", ["", "whsec_", "sk_test_example", "sk_live_example"])
def test_invalid_configuration_fails_closed(secret):
    with pytest.raises(ValueError):
        create_app(secret)


def test_repeated_sample_is_acknowledged_without_processing(client):
    # X04 proves signatures only. Durable event-ID deduplication remains B03.
    assert post(client).status_code == 200
    assert post(client).json()["payment_processed"] is False


def test_loopback_http_raw_body_callback():
    # Exercise the actual HTTP server/parser, beyond the in-process ASGI client.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(DEMO_SECRET), log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            url = f"http://127.0.0.1:{port}/stripe/webhook"
            with httpx.Client(timeout=5, trust_env=False) as client:
                for body, header, expected in (
                    (BODY, signature(), 200),
                    (BODY + b"\n", signature(), 400),
                    (BODY, signature(timestamp=int(time.time()) - 601), 400),
                ):
                    response = client.post(url, content=body, headers={"Stripe-Signature": header})
                    assert response.status_code == expected
                    if expected == 200:
                        assert response.json()["payment_processed"] is False
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()
