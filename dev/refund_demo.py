"""Prepare a real local booking/Stripe test Checkout; never fabricate payment state."""

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values

APIS = {"tenant": 8002, "scheduling": 8003, "billing": 8009}


class Demo:
    def __init__(self, root, client):
        self.client = client
        self.path = root / ".local/refund-demo.json"
        self.identity = dotenv_values(root / "services/identity/.env")
        self.billing = dotenv_values(root / "services/billing/.env")
        for name in ("identity", "tenant", "scheduling", "billing"):
            if (
                dotenv_values(root / f"services/{name}/.env").get("SERVICE_ENVIRONMENT")
                != "local"
            ):
                raise ValueError(
                    "This helper requires explicit local service environments."
                )
        self.key = self.billing.get("SERVICE_STRIPE_SECRET_KEY", "")
        if not re.fullmatch(r"sk_test_[A-Za-z0-9]+", self.key):
            raise ValueError(
                "Configure a Stripe test secret key before preparing the demo."
            )
        self.tokens = {}
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2) + "\n")

    def token(self, role):
        if role not in self.tokens:
            response = self.client.post(
                "http://127.0.0.1:4566/",
                headers={
                    "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
                    "Content-Type": "application/x-amz-json-1.1",
                },
                json={
                    "AuthFlow": "USER_PASSWORD_AUTH",
                    "ClientId": self.identity["SERVICE_AUTH_CLIENT_ID"],
                    "AuthParameters": {
                        "USERNAME": f"{role}@example.test",
                        "PASSWORD": "LocalDemo123!",
                    },
                },
            )
            if response.status_code != 200:
                raise ValueError(
                    "Local demo sign-in failed; seed the demo accounts first."
                )
            self.tokens[role] = response.json()["AuthenticationResult"]["AccessToken"]
        return self.tokens[role]

    def api(
        self,
        service,
        path,
        *,
        role="patient",
        method="GET",
        body=None,
        params=None,
        key=None,
    ):
        headers = {"Authorization": "Bearer " + self.token(role)}
        if key:
            headers["Idempotency-Key"] = key
        response = self.client.request(
            method,
            f"http://127.0.0.1:{APIS[service]}{path}",
            headers=headers,
            json=body,
            params=params,
        )
        if response.is_error:
            try:
                code = response.json()["error"]["code"]
            except (ValueError, KeyError, TypeError):
                code = "unavailable"
            raise ValueError(
                f"{service} API refused the request ({response.status_code}: {code})."
            )
        return response.json()

    def records(self):
        if not self.state.get("appointment_id"):
            raise ValueError("Run prepare first.")
        appointment = self.api(
            "scheduling", "/appointments/" + self.state["appointment_id"]
        )
        payment = (
            self.api("billing", "/payments/" + appointment["payment_id"])
            if appointment.get("payment_id")
            else None
        )
        return appointment, payment

    def prepare(self, tenant_id, fresh):
        if self.state.get("appointment_id"):
            appointment, payment = self.records()
            if fresh:
                if not (
                    (
                        appointment["status"] == "expired"
                        and (not payment or payment["status"] == "failed")
                    )
                    or (payment and payment["status"] == "refunded")
                ):
                    raise ValueError(
                        "Finish/refund the existing example before using --new."
                    )
                self.state = {}
            elif tenant_id and tenant_id != self.state["tenant_id"]:
                raise ValueError("The saved example belongs to another clinic.")
        if not self.state:
            destinations = json.loads(
                self.billing.get("SERVICE_STRIPE_DESTINATIONS", "{}")
            )
            tenant_id = tenant_id or next(iter(destinations), None)
            if not tenant_id or tenant_id not in destinations:
                raise ValueError(
                    "Choose a clinic with a configured Stripe test destination."
                )
            clinic = self.api("tenant", "/clinics/" + tenant_id, role="clinic")
            start = datetime.now(timezone.utc)
            params = {
                "from": start.isoformat(),
                "to": (start + timedelta(days=7)).isoformat(),
                "limit": 100,
            }
            slot = None
            while True:
                page = self.api(
                    "scheduling", f"/clinics/{tenant_id}/slots", params=params
                )
                slot = next(
                    (s for s in page["items"] if s["availability"] == "available"), None
                )
                if slot or not page["next_cursor"]:
                    break
                params["cursor"] = page["next_cursor"]
            if slot is None:
                raise ValueError(
                    "Add an available doctor slot within the next seven days, then rerun."
                )
            appointment = self.api(
                "scheduling",
                "/appointments",
                method="POST",
                body={"tenant_id": tenant_id, "slot_id": slot["slot_id"]},
            )
            self.state = {
                "tenant_id": tenant_id,
                "clinic_name": clinic["name"],
                "appointment_id": appointment["appointment_id"],
                "checkout_key": "RF08-" + uuid4().hex,
            }
            self.save()  # Retain the same booking/key if checkout creation is interrupted.
        appointment, payment = self.records()
        if payment and payment["status"] != "pending":
            return self.report()
        checkout = self.api(
            "billing",
            "/consultation-checkouts",
            method="POST",
            body={"appointment_id": appointment["appointment_id"]},
            key=self.state["checkout_key"],
        )
        self.state.update(
            payment_id=checkout["payment"]["payment_id"],
            checkout_url=checkout["checkout_url"],
        )
        self.save()
        result = self.report()
        result.update(
            checkout_url=checkout["checkout_url"], pay_before=checkout["expires_at"]
        )
        return result

    def cancel(self):
        appointment, payment = self.records()
        if not payment or payment["status"] != "succeeded":
            raise ValueError(
                "Complete Stripe test Checkout and wait for payment success first."
            )
        if appointment["status"] not in {"confirmed", "cancelled"}:
            raise ValueError("Wait for scheduling confirmation before cancelling.")
        self.api(
            "scheduling",
            "/appointments/" + appointment["appointment_id"] + "/cancel",
            role="clinic",
            method="POST",
            body={"reason": "Stripe sandbox refund demonstration"},
        )
        return self.report("refundable")

    def report(self, expect=None):
        appointment, payment = self.records()
        history = (
            self.api(
                "billing",
                "/payments/" + payment["payment_id"] + "/refunds",
                role="clinic",
            )
            if payment
            else []
        )
        result = {
            "clinic": self.state["clinic_name"],
            "tenant_id": appointment["tenant_id"],
            "appointment_id": appointment["appointment_id"],
            "appointment_status": appointment["status"],
            "payment_id": payment["payment_id"] if payment else None,
            "payment_status": payment["status"] if payment else None,
            "payment_resolution": appointment["payment_resolution"],
            "amount": payment["amount"]
            if payment
            else appointment["consultation_price"],
            "refund_availability": payment["refund_availability"] if payment else None,
            "refund_statuses": [r["status"] for r in history],
        }
        if expect:
            linked = (
                payment
                and payment["appointment_id"] == appointment["appointment_id"]
                and all(
                    payment[f] == appointment[f] for f in ("tenant_id", "patient_id")
                )
                and payment["amount"] == appointment["consultation_price"]
            )
            passed = (
                linked
                and {
                    "paid": payment["status"] == "succeeded"
                    and appointment["status"] == "confirmed",
                    "refundable": payment["status"] == "succeeded"
                    and appointment["status"] == "cancelled"
                    and payment["refund_availability"] == "available"
                    and not history,
                    "refunded": payment["status"] == "refunded"
                    and appointment["payment_resolution"] == "refunded"
                    and any(r["status"] == "succeeded" for r in history),
                }[expect]
            )
            if not passed:
                raise ValueError(
                    f"Expected {expect}; current state: {json.dumps(result)}"
                )
            result["verified"] = expect
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare", help="Reserve a slot and create/resume Stripe test Checkout"
    )
    prepare.add_argument("--tenant", type=lambda value: str(UUID(value)))
    prepare.add_argument(
        "--new",
        action="store_true",
        help="Replace an expired or fully refunded example",
    )
    commands.add_parser(
        "cancel", help="Cancel only the saved, successfully paid demo booking"
    )
    status = commands.add_parser(
        "status", help="Read authoritative appointment/payment/refund state"
    )
    status.add_argument("--expect", choices=("paid", "refundable", "refunded"))
    args = parser.parse_args()
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            demo = Demo(args.root.resolve(), client)
            if args.command == "prepare":
                result = demo.prepare(args.tenant, args.new)
            elif args.command == "cancel":
                result = demo.cancel()
            else:
                result = demo.report(args.expect)
            print(json.dumps(result, indent=2))
    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
        # Never print response bodies, tokens or provider credentials.
        parser.exit(
            1, f"{error if isinstance(error, ValueError) else type(error).__name__}\n"
        )


if __name__ == "__main__":
    main()
