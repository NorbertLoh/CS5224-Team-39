"""Read-only I03 check: actual issued prescription, two payments and one delivery.

Run with fulfilment's installed dependencies. The database connection enforces
read-only transactions. This checks persisted sandbox evidence, not physical
delivery or deployed AWS. The synthetic courier order may be cancelled afterward.
"""

import argparse
import sys
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev"))
from floci.check_auth import cognito, login  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("appointment_id", type=UUID)
    parser.add_argument("order_id", type=UUID)
    parser.add_argument("consultation_payment_id", type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    args = parser.parse_args()
    identity = dotenv_values(args.config_root / "services/identity/.env")
    config = dotenv_values(args.config_root / "services/fulfilment/.env")
    database = make_url(config["SERVICE_DATABASE_URL"])
    if (
        not identity["SERVICE_AUTH_ISSUER"].startswith("http://localhost:4566/")
        or database.host not in {"localhost", "127.0.0.1"}
        or database.port != 55411
    ):
        parser.error("Use the documented local Floci and persistent database on 55411")

    def check(name, passed):
        print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
        if not passed:
            raise AssertionError(name)

    with httpx.Client(timeout=20, trust_env=False) as http:
        tokens = login(
            http,
            identity["SERVICE_AUTH_CLIENT_ID"],
            callback="http://127.0.0.1:5173/auth/callback",
            username="patient@example.test",
        )
        try:

            def get(port, path):
                result = http.get(
                    f"http://127.0.0.1:{port}" + path,
                    headers={"Authorization": "Bearer " + tokens["access_token"]},
                )
                result.raise_for_status()
                return result.json()

            appointment = get(8003, f"/appointments/{args.appointment_id}")
            order = get(8006, f"/orders/{args.order_id}")
            prescription = get(
                8005, "/api/v1/clinical-records/prescriptions/" + order["prescription_id"]
            )
            consultation = get(8009, f"/payments/{args.consultation_payment_id}")
            medication = get(8009, "/payments/" + order["payment_id"])
            delivery = get(8006, "/deliveries/" + order["delivery_id"])
            quote = get(8006, "/quotes/" + order["quote_id"])
            check("consultation completed", appointment["status"] == "completed")
            check(
                "issued prescription belongs to this consultation",
                prescription["status"] == "issued"
                and prescription["issued_at"] is not None
                and prescription["appointment_id"] == str(args.appointment_id)
                and order["appointment_id"] == str(args.appointment_id),
            )
            check(
                "patient and clinic links agree across the journey",
                all(
                    resource[field] == appointment[field]
                    for resource in (prescription, order, consultation, medication)
                    for field in ("patient_id", "tenant_id")
                )
                and delivery["tenant_id"] == appointment["tenant_id"],
            )
            check(
                "order quantities come from the issued prescription",
                sorted((i["prescription_item_id"], i["quantity"]) for i in order["items"])
                == sorted((i["prescription_item_id"], i["quantity"]) for i in prescription["items"])
                and bool(order["items"]),
            )
            check(
                "consultation and medication are separate succeeded payments",
                consultation["purpose"] == "consultation"
                and consultation["appointment_id"] == str(args.appointment_id)
                and medication["purpose"] == "medication_delivery"
                and medication["order_id"] == str(args.order_id)
                and medication["quote_id"] == order["quote_id"]
                and consultation["payment_id"] != medication["payment_id"]
                and consultation["status"] == medication["status"] == "succeeded",
            )
            check(
                "medication payment matches the accepted quote and trusted totals",
                quote["order_id"] == str(args.order_id)
                and quote["status"] == "accepted"
                and medication["amount"] == quote["total"] == order["total"]
                and order["total"]["amount_minor"]
                == order["medication_subtotal"]["amount_minor"]
                + order["delivery_fee"]["amount_minor"],
            )
            check(
                "paid and ready order links to its provider delivery",
                order["payment_status"] == "succeeded"
                and order["medicine_status"] == "ready"
                and delivery["order_id"] == str(args.order_id)
                and delivery["status"] in {"submitted", "picked_up", "delivered", "cancelled"},
            )
            with psycopg.connect(
                database.set(drivername="postgresql").render_as_string(hide_password=False),
                autocommit=True,
                options="-c default_transaction_read_only=on",
            ) as db:
                rows = db.execute(
                    "SELECT delivery_id, provider_order_id, send_started_at "
                    "FROM fulfilment.deliveries WHERE order_id=%s",
                    (args.order_id,),
                ).fetchall()
                check(
                    "exactly one persisted submission with a provider reference",
                    len(rows) == 1
                    and str(rows[0][0]) == order["delivery_id"]
                    and bool(rows[0][1])
                    and rows[0][2] is not None,
                )
            print(f"I03 persisted-state checks passed; delivery status={delivery['status']}.")
            print("Provider and transport observations: docs/I03-local-journey.md")
        finally:
            verification_failed = sys.exc_info()[0] is not None
            try:
                result = cognito(
                    http,
                    "RevokeToken",
                    ClientId=identity["SERVICE_AUTH_CLIENT_ID"],
                    Token=tokens["refresh_token"],
                )
                result.raise_for_status()
            except Exception:
                if not verification_failed:
                    raise
                print("Verification failed; token revocation also needs retry.", file=sys.stderr)


if __name__ == "__main__":
    main()
