"""X03 feasibility CLI. No application routes, database writes or webhook handling."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

AMOUNT = 5000
FEE = 500
CURRENCY = "sgd"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class SpikeError(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_config(path):
    """Read only provider variables; process environment takes precedence. No shell evaluation."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name in {"STRIPE_SECRET_KEY", "STRIPE_CONNECTED_ACCOUNT_ID"}:
                values[name] = value.strip().strip("\"'")
    return {
        name: os.environ.get(name, values.get(name, ""))
        for name in ("STRIPE_SECRET_KEY", "STRIPE_CONNECTED_ACCOUNT_ID")
    }


def require(condition, message):
    if not condition:
        raise SpikeError(message)


def account_id(value):
    require(bool(re.fullmatch(r"acct_[A-Za-z0-9]+", value)), "Set a connected acct_ ID")
    return value


class StripeTestClient:
    def __init__(self, key):
        require(
            bool(re.fullmatch(r"sk_test_[A-Za-z0-9]+", key)),
            "Set STRIPE_SECRET_KEY to a test secret key (sk_test_); live keys refused",
        )
        self.key = key
        self.opener = build_opener(NoRedirects())

    def request(self, path, fields=None, idempotency_key=None):
        headers = {"Authorization": f"Bearer {self.key}", "Stripe-Version": "2024-06-20"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        data = None if fields is None else urlencode(fields).encode()
        request = Request("https://api.stripe.com/v1/" + path, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except HTTPError as error:
            # Do not print raw provider errors, request bodies, URLs or credentials.
            raise SpikeError(
                f"Stripe HTTP {error.code}; inspect the test Dashboard API logs"
            ) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise SpikeError(
                "Stripe transport/JSON failure; inspect connectivity and retry"
            ) from None
        if "livemode" in result:
            require(result["livemode"] is False, "Live provider object refused")
        return result


def check_account(client, destination):
    account = client.request(f"accounts/{destination}")
    require(account.get("id") == destination, "Connected account identity mismatch")
    require(
        account.get("capabilities", {}).get("transfers") == "active",
        "Connected test account needs active transfers capability; finish test onboarding",
    )
    return {
        "connected_account_id": destination,
        "transfers": "active",
        "charges_enabled": account.get("charges_enabled"),
        "country": account.get("country"),
    }


def checkout_fields(destination, run_id):
    return {
        "mode": "payment",
        "payment_method_types[0]": "card",
        "line_items[0][price_data][currency]": CURRENCY,
        "line_items[0][price_data][unit_amount]": AMOUNT,
        "line_items[0][price_data][product_data][name]": "X03 synthetic consultation",
        "line_items[0][quantity]": 1,
        "payment_intent_data[application_fee_amount]": FEE,
        "payment_intent_data[transfer_data][destination]": destination,
        "payment_intent_data[metadata][task]": "X03",
        "metadata[task]": "X03",
        "metadata[run_id]": run_id,
        "success_url": "http://localhost:5173/?x03=success&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "http://localhost:5173/?x03=cancel",
    }


def verify_evidence(session, intent, charge, fee, transfer, destination):
    """Compare independent provider objects; an unpaid redirect cannot pass."""
    for obj in (session, intent, charge, fee, transfer):
        require(obj.get("livemode") is False, "Missing test-mode evidence")
    require(session.get("metadata", {}).get("task") == "X03", "Not an X03 session")
    require(
        session.get("status") == "complete" and session.get("payment_status") == "paid",
        "Checkout is not complete and paid",
    )
    require(
        intent.get("status") == "succeeded" and charge.get("paid") is True,
        "Payment has not succeeded",
    )
    require(
        charge.get("captured") is True and charge.get("refunded") is False,
        "Charge is uncaptured or refunded",
    )
    require(
        charge.get("amount_refunded") == 0 and transfer.get("amount_reversed") == 0,
        "Charge/transfer has been partially reversed",
    )
    require(
        session.get("payment_intent") == intent.get("id")
        and intent.get("latest_charge") == charge.get("id")
        and charge.get("payment_intent") == intent.get("id"),
        "Payment linkage mismatch",
    )
    # Destination fees reference the platform charge and the clinic payment separately.
    require(
        charge.get("application_fee") == fee.get("id")
        and fee.get("originating_transaction") == charge.get("id")
        and bool(transfer.get("destination_payment"))
        and fee.get("charge") == transfer.get("destination_payment")
        and charge.get("transfer") == transfer.get("id")
        and transfer.get("source_transaction") == charge.get("id"),
        "Fee/transfer linkage mismatch",
    )
    require(session.get("amount_total") == AMOUNT, "Checkout total mismatch")
    for obj in (intent, charge, transfer):
        require(obj.get("amount") == AMOUNT, "Payment/transfer amount mismatch")
    require(
        intent.get("application_fee_amount") == FEE and fee.get("amount") == FEE,
        "Commission mismatch",
    )
    require(
        fee.get("refunded") is False and fee.get("amount_refunded") == 0,
        "Application fee has been refunded",
    )
    require(
        all(obj.get("currency") == CURRENCY for obj in (session, intent, charge, fee, transfer)),
        "Currency mismatch",
    )
    require(
        intent.get("transfer_data", {}).get("destination") == destination
        and transfer.get("destination") == destination
        and fee.get("account") == destination,
        "Connected destination mismatch",
    )
    return {
        "session_id": session["id"],
        "payment_intent_id": intent["id"],
        "charge_id": charge["id"],
        "application_fee_id": fee["id"],
        "transfer_id": transfer["id"],
        "connected_account_id": destination,
        "currency": CURRENCY,
        "amount_minor": AMOUNT,
        "application_fee_minor": FEE,
        "clinic_gross_minor": AMOUNT - FEE,
        "note": "Platform commission is gross; Stripe processing fees reduce platform net.",
    }


def retrieve(client, kind, identifier, prefix):
    require(
        isinstance(identifier, str) and bool(re.fullmatch(prefix + r"[A-Za-z0-9]+", identifier)),
        f"Missing or invalid {kind} ID",
    )
    return client.request(f"{kind}/{identifier}")


def inspect_payment(client, session_id, destination):
    session = retrieve(client, "checkout/sessions", session_id, "cs_test_")
    intent = retrieve(client, "payment_intents", session.get("payment_intent"), "pi_")
    charge = retrieve(client, "charges", intent.get("latest_charge"), "ch_")
    fee = retrieve(client, "application_fees", charge.get("application_fee"), "fee_")
    transfer = retrieve(client, "transfers", charge.get("transfer"), "tr_")
    evidence = verify_evidence(session, intent, charge, fee, transfer, destination)
    return {"mode": "stripe-test", "provider_verified": True, **evidence}


def demo():
    """Explicitly labelled adapter for offline demo continuity, never provider evidence."""
    return {
        "mode": "demo-fixture",
        "provider_verified": False,
        "task_complete": False,
        "currency": CURRENCY,
        "amount_minor": AMOUNT,
        "application_fee_minor": FEE,
        "clinic_gross_minor": AMOUNT - FEE,
        "checkout_status": "simulated-paid",
        "note": "No Stripe call or usable checkout URL. X03/B02/X04 remain unverified.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "account", "create", "inspect"))
    parser.add_argument("--env-file", type=Path, default=ENV_FILE)
    parser.add_argument("--run-id", help="Unique attempt ID; reuse only to retry the same create")
    parser.add_argument("--session-id")
    args = parser.parse_args()
    try:
        if args.command == "demo":
            result = demo()
        else:
            config = load_config(args.env_file)
            client = StripeTestClient(config["STRIPE_SECRET_KEY"])
            destination = account_id(config["STRIPE_CONNECTED_ACCOUNT_ID"])
            account = check_account(client, destination)
            if args.command == "account":
                result = {"mode": "stripe-test", **account}
            elif args.command == "create":
                require(
                    bool(re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id or "")),
                    "Supply --run-id with 1-80 letters, digits, underscores or hyphens",
                )
                session = client.request(
                    "checkout/sessions",
                    checkout_fields(destination, args.run_id),
                    f"X03-{destination}-{args.run_id}",
                )
                require(session.get("livemode") is False, "Missing test-mode evidence")
                result = {
                    "mode": "stripe-test",
                    "provider_verified": False,
                    "session_id": session["id"],
                    "checkout_url": session["url"],
                    "note": "Open checkout_url and pay with a test card, then run inspect.",
                }
            else:
                result = inspect_payment(client, args.session_id, destination)
        print(json.dumps(result, indent=2))
        return 0
    except (SpikeError, OSError) as error:
        print(
            str(error) if isinstance(error, SpikeError) else "Cannot read local config",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
