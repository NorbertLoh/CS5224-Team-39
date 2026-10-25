"""Replay an existing Stripe test event through a local billing HTTP receiver.

Retrieves the genuine provider body, signs it locally and resends it. This is an
operator replay, not a fresh delivery from Stripe. No payment is created.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/billing"))
from app.settings import Settings  # noqa: E402


def check(name, passed):
    print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
    if not passed:
        raise AssertionError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payment_id", type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    parser.add_argument("--billing-url", default="http://127.0.0.1:18009")
    args = parser.parse_args()
    settings = Settings(_env_file=args.config_root / "services/billing/.env")
    url = make_url(settings.database_url.get_secret_value())
    target = urlsplit(args.billing_url)
    if (
        settings.environment not in {"local", "test"}
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 55411
        or url.username != "billing"
        or url.database != "telelink"
        or target.scheme != "http"
        or target.hostname not in {"localhost", "127.0.0.1"}
        or target.port not in {8009, 18009}
        or target.path not in {"", "/"}
        or target.username
        or target.password
        or target.query
        or target.fragment
        or not settings.stripe_secret_key
        or not settings.stripe_secret_key.get_secret_value().startswith("sk_test_")
        or not settings.stripe_webhook_secret
    ):
        parser.error("Use local billing on 55411, a loopback receiver and Stripe test credentials")

    with (
        psycopg.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as db,
        httpx.Client(timeout=20, trust_env=False) as http,
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
        response = http.get(args.billing_url.rstrip("/") + "/health/live")
        response.raise_for_status()
        check("actual billing HTTP receiver", response.json().get("service") == "billing")
        body = json.dumps(event, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(
            settings.stripe_webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        headers = {"Stripe-Signature": f"t={timestamp},v1={digest}"}
        endpoint = args.billing_url.rstrip("/") + "/webhooks/stripe"
        response = http.post(endpoint, content=body + b" ", headers=headers)
        check("tampered replay is rejected", response.status_code == 400)
        check("rejected replay leaves durable state unchanged", snapshot() == before)

        def resend(_):
            result = http.post(endpoint, content=body, headers=headers)
            return result.status_code == 200 and result.json() == {"received": True}

        with ThreadPoolExecutor(max_workers=4) as pool:
            check("four concurrent signed replays acknowledged", all(pool.map(resend, range(4))))
        check(
            "one receipt, same payment and same success outbox after replay", snapshot() == before
        )
        print("Q03 billing replay passed; body retrieved from Stripe and re-signed locally.")


if __name__ == "__main__":
    main()
