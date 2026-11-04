"""I02 local journey helper: seed a catalogue item, then verify consultation -> PDF.

Run with services/identity/.venv/Scripts/python.exe against the local stack in
docs/I02-local-journey.md. It uses the Floci demo accounts and real service APIs
only. It never resets schemas or edits appointments, records or documents.

  seed-catalogue TENANT_ID  Add one active medication to the clinic catalogue as
                            clinic@example.test (there is no catalogue UI).
  verify APPOINTMENT_ID     Check the appointment completed, its prescription was
                            issued, and the patient can download its private PDF.
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

SCHEDULING = "http://127.0.0.1:8003"
RECORDS = "http://127.0.0.1:8005/api/v1/clinical-records"
FULFILMENT = "http://127.0.0.1:8006"
DOCUMENTS = "http://127.0.0.1:8007/api/v1/document/documents"


def token(client, role):
    client_id = dotenv_values(ROOT / "services/identity/.env")["SERVICE_AUTH_CLIENT_ID"]
    client.cookies.clear()
    # cognito.sh always registers the 127.0.0.1 callback, whatever COGNITO_CALLBACK_URL is.
    callback = "http://127.0.0.1:5173/auth/callback"
    tokens = login(client, client_id, callback=callback, username=f"{role}@example.test")
    return tokens["access_token"]


def get(client, url, access_token, **params):
    response = client.get(url, headers={"Authorization": "Bearer " + access_token}, params=params)
    response.raise_for_status()
    return response.json()


def seed_catalogue(client, tenant_id):
    response = client.put(
        f"{FULFILMENT}/clinics/{tenant_id}/catalogue/{uuid4()}",
        headers={"Authorization": "Bearer " + token(client, "clinic")},
        json={
            "display_name": "Paracetamol 500 mg tablet",
            "unit_label": "tablet",
            "unit_price": {"amount_minor": 20, "currency": "SGD"},
            "active": True,
        },
    )
    response.raise_for_status()
    item = response.json()
    print(f"Catalogue item {item['display_name']} ({item['medication_id']}) added")


def verify(client, appointment_id):
    patient = token(client, "patient")
    appointment = get(client, f"{SCHEDULING}/appointments/{appointment_id}", patient)
    prescriptions = get(client, f"{RECORDS}/prescriptions", patient, appointment_id=appointment_id)
    documents = get(client, DOCUMENTS, patient, appointment_id=appointment_id)
    issued = [item for item in prescriptions["items"] if item["status"] == "issued"]
    pdfs = [
        item
        for item in documents["items"]
        if item["kind"] == "prescription_pdf"
        and item["status"] == "ready"
        and item["prescription_id"] in {p["prescription_id"] for p in issued}
    ]
    pdf = b""
    if pdfs:
        download = get(client, f"{DOCUMENTS}/{pdfs[0]['document_id']}/download", patient)
        # The signed URL is fetched without the API bearer token, as the browser does.
        pdf = httpx.get(download["download_url"], timeout=15, trust_env=False).content
    checks = {
        "appointment completed": appointment["status"] == "completed",
        "prescription issued for this appointment": len(issued) == 1 and bool(issued[0]["items"]),
        "prescription PDF ready for the patient": len(pdfs) == 1,
        "signed download returns a PDF": pdf.startswith(b"%PDF"),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    if issued and pdfs:
        print(
            f"appointment={appointment_id} prescription={issued[0]['prescription_id']} "
            f"document={pdfs[0]['document_id']} pdf_bytes={len(pdf)}"
        )
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-catalogue").add_argument("tenant_id")
    commands.add_parser("verify").add_argument("appointment_id")
    args = parser.parse_args()
    with httpx.Client(timeout=15, trust_env=False) as client:
        if args.command == "seed-catalogue":
            seed_catalogue(client, args.tenant_id)
        elif not verify(client, args.appointment_id):
            sys.exit(1)


if __name__ == "__main__":
    main()
