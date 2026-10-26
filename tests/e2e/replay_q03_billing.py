"""Replay an existing Stripe test event through a local billing HTTP receiver.

Retrieves the genuine provider body, signs it locally and resends it. This is an
operator replay, not a fresh delivery from Stripe. No payment is created.
"""

import argparse
import hashlib
import hmac
import json
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from pathlib import Path
from threading import Thread
from uuid import UUID

import httpx
import psycopg
import uvicorn
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/billing"))
from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402


def check(name, passed):
    print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
    if not passed:
        raise AssertionError(name)


@contextmanager
def receiver(settings):
    """Bind the real HTTP app to the exact settings used for database snapshots."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(create_app(settings), log_config=None, access_log=False)
        )
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError("Temporary billing receiver did not start")
            yield address
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("Temporary billing receiver did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payment_id", type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    args = parser.parse_args()
    settings = Settings(_env_file=args.config_root / "services/billing/.env")
    url = make_url(settings.database_url.get_secret_value())
    if (
        settings.environment not in {"local", "test"}
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 55411
        or url.username != "billing"
        or url.database != "telelink"
        or not settings.stripe_secret_key
        or not settings.stripe_secret_key.get_secret_value().startswith("sk_test_")
        or not settings.stripe_webhook_secret
    ):
        parser.error("Use local billing on 55411 and Stripe test credentials")

    with (
        psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as db,
        httpx.Client(timeout=20, trust_env=False) as http,
        ExitStack() as stack,
    ):

        def snapshot():
            payment = db.execute(
                "SELECT to_jsonb(p) AS data FROM billing.payments p WHERE payment_id=%s",
                (args.payment_id,),
            ).fetchone()
            receipts = db.execute(
                "SELECT to_jsonb(r) AS data FROM billing.stripe_webhook_events r "
                "WHERE object_data->'metadata'->>'payment_id'=%s ORDER BY event_id",
                (str(args.payment_id),),
            ).fetchall()
            outbox = db.execute(
                "SELECT to_jsonb(e) AS data FROM billing.event_outbox e "
                "WHERE detail::jsonb->'data'->>'payment_id'=%s ORDER BY event_id",
                (str(args.payment_id),),
            ).fetchall()
            return payment, receipts, outbox

        before = snapshot()
        payment = before[0]["data"] if before[0] else None
        check(
            "existing genuine succeeded Stripe payment",
            payment is not None
            and payment["provider"] == "stripe"
            and payment["status"] == "succeeded"
            and bool(payment["provider_checkout_id"]),
        )
        check(
            "one original published payment-success event",
            len(before[2]) == 1 and before[2][0]["data"]["published_at"] is not None,
        )
        receipts = [
            row["data"]
            for row in before[1]
            if row["data"]["event_type"] == "checkout.session.completed"
        ]
        check("one already-processed Checkout receipt", len(receipts) == 1)
        receipt = receipts[0]
        check("receipt is processed", receipt["status"] == "processed")
        response = http.get(
            "https://api.stripe.com/v1/events/" + receipt["event_id"],
            auth=(settings.stripe_secret_key.get_secret_value(), ""),
        )
        response.raise_for_status()
        event = response.json()
        obj = event.get("data", {}).get("object", {})
        check(
            "provider event matches the stored payment and receipt",
            event.get("id") == receipt["event_id"]
            and event.get("type") == "checkout.session.completed"
            and event.get("livemode") is False
            and obj.get("id") == payment["provider_checkout_id"]
            and obj.get("client_reference_id") == str(args.payment_id)
            and obj.get("payment_intent") == payment["provider_payment_id"]
            and obj.get("amount_total") == payment["amount_minor"]
            and obj.get("payment_status") == "paid",
        )
        billing_url = stack.enter_context(receiver(settings))
        response = http.get(billing_url + "/health/live")
        response.raise_for_status()
        check(
            "actual billing HTTP receiver", response.json().get("service") == "billing"
        )
        body = json.dumps(event, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(
            settings.stripe_webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={timestamp},v1={digest}"}
        endpoint = billing_url + "/webhooks/stripe"
        response = http.post(endpoint, content=body + b" ", headers=headers)
        check("tampered replay is rejected", response.status_code == 400)
        check("rejected replay leaves durable state unchanged", snapshot() == before)

        def resend(_):
            result = http.post(endpoint, content=body, headers=headers)
            return result.status_code == 200 and result.json() == {"received": True}

        with ThreadPoolExecutor(max_workers=4) as pool:
            check(
                "four concurrent signed replays acknowledged",
                all(pool.map(resend, range(4))),
            )
        check(
            "one receipt, same payment and same success outbox after replay",
            snapshot() == before,
        )
        print(
            "Q03 billing replay passed; body retrieved from Stripe and re-signed locally."
        )


if __name__ == "__main__":
    main()
