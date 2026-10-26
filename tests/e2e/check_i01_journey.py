"""I01 local journey helper: submit a pending clinic, then verify the paid booking.

Run with services/identity/.venv/Scripts/python.exe against the local stack in
docs/I01-local-journey.md. It uses the four Floci demo accounts and real service
APIs only. It never resets schemas, edits other clinics or changes payment state.

  submit-clinic          Create a new pending clinic owned by clinic@example.test.
  verify APPOINTMENT_ID  Check the clinic is active, the appointment is confirmed
                         and its consultation payment succeeded for the same amount.
"""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev"))
from floci.check_auth import login  # noqa: E402

IDENTITY = "http://127.0.0.1:8001"
TENANT = "http://127.0.0.1:8002"
SCHEDULING = "http://127.0.0.1:8003"
BILLING = "http://127.0.0.1:8009"


def token(client, role):
    client_id = dotenv_values(ROOT / "services/identity/.env")["SERVICE_AUTH_CLIENT_ID"]
    client.cookies.clear()
    # cognito.sh always registers the 127.0.0.1 callback, whatever COGNITO_CALLBACK_URL is.
    callback = "http://127.0.0.1:5173/auth/callback"
    tokens = login(
        client, client_id, callback=callback, username=f"{role}@example.test"
    )
    return tokens["access_token"]


def get(client, base, path, access_token):
    response = client.get(
        base + path, headers={"Authorization": "Bearer " + access_token}
    )
    response.raise_for_status()
    return response.json()


def submit_clinic(client):
    response = client.post(
        TENANT + "/clinics",
        headers={"Authorization": "Bearer " + token(client, "clinic")},
        json={
            "slug": "i01-" + uuid4().hex[:8],
            "name": "I01 Journey Clinic",
            "branding": {
                "primary_color": "#156B63",
                "logo_url": None,
                "description": "Synthetic clinic for the I01 local journey.",
            },
            "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
        },
    )
    response.raise_for_status()
    clinic = response.json()
    print(
        f"Submitted {clinic['status']} clinic {clinic['slug']} (tenant {clinic['tenant_id']})"
    )


def verify(client, appointment_id):
    patient = token(client, "patient")
    appointment = get(client, SCHEDULING, f"/appointments/{appointment_id}", patient)
    payment = get(client, BILLING, f"/payments/{appointment['payment_id']}", patient)
    clinic = get(
        client,
        TENANT,
        f"/clinics/{appointment['tenant_id']}",
        token(client, "platform"),
    )
    checks = {
        "clinic approved and active": clinic["status"] == "active",
        "appointment confirmed": appointment["status"] == "confirmed",
        "appointment payment resolution confirmed": appointment["payment_resolution"]
        == "confirmed",
        "payment succeeded": payment["status"] == "succeeded",
        "payment is the consultation for this appointment": payment["purpose"]
        == "consultation"
        and payment["appointment_id"] == appointment_id,
        "same patient and clinic": payment["patient_id"] == appointment["patient_id"]
        and payment["tenant_id"] == appointment["tenant_id"],
        "amount matches booked price": payment["amount"]
        == appointment["consultation_price"],
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    amount = payment["amount"]
    print(
        f"clinic={clinic['slug']} appointment={appointment_id} payment={payment['payment_id']} "
        f"amount={amount['currency']} {amount['amount_minor'] / 100:.2f}"
    )
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("submit-clinic")
    commands.add_parser("verify").add_argument("appointment_id")
    args = parser.parse_args()
    with httpx.Client(timeout=15, trust_env=False) as client:
        if args.command == "submit-clinic":
            submit_clinic(client)
        elif not verify(client, args.appointment_id):
            sys.exit(1)


if __name__ == "__main__":
    main()
