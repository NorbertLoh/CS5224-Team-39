"""Exercise real R04 adapters with isolated synthetic data; never reset schemas.

Requires running local services/Vite and SERVICE_AUTH_CLIENT_ID in identity/.env.
An in-progress scheduling row is test setup only, not a real payment/consultation.
Only this run's clinical/scheduling rows are deleted; its clinic/medication are
suspended/deactivated and its doctor membership/tokens revoked afterward.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
from check_scheduling_integration import request
from dotenv import dotenv_values
from floci.check_auth import cognito, login
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def local_url(name, default):
    value = os.environ.get(name, default)
    url = urlsplit(value)
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError(f"{name} must target localhost HTTP")
    return value.rstrip("/")


def database(name, service):
    url = os.environ.get(name) or dotenv_values(ROOT / f"services/{service}/.env").get(
        "SERVICE_DATABASE_URL"
    )
    if not url:
        raise ValueError(f"Set {name} to the running local service database")
    engine = create_engine(url)
    if engine.url.host not in {"localhost", "127.0.0.1"}:
        raise ValueError("Synthetic setup is restricted to localhost databases")
    return engine


def main():
    identity = local_url("R04_IDENTITY_URL", "http://127.0.0.1:8001")
    tenant = local_url("R04_TENANT_URL", "http://127.0.0.1:8002")
    fulfilment = local_url("R04_FULFILMENT_URL", "http://127.0.0.1:8006")
    web = local_url("R04_WEB_URL", "http://127.0.0.1:5173")
    client_id = dotenv_values(ROOT / "services/identity/.env")["SERVICE_AUTH_CLIENT_ID"]
    scheduling = database("R04_SCHEDULING_DATABASE_URL", "scheduling")
    records = database("R04_RECORDS_DATABASE_URL", "clinical_records")
    tokens, clinic, doctor = {}, None, None
    slot, appointment, medication = uuid4(), uuid4(), uuid4()
    medicine = dict(
        display_name="R04 synthetic catalogue medication",
        unit_label="unit",
        unit_price={"amount_minor": 100, "currency": "SGD"},
        active=True,
    )
    with httpx.Client(timeout=20, trust_env=False) as client:
        try:
            for role in ("doctor", "patient", "clinic", "platform"):
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
            admin, platform = [tokens[role]["access_token"] for role in ("clinic", "platform")]
            doctor = request(client, "GET", identity, "/me", tokens["doctor"]["access_token"])[
                "subject_id"
            ]
            patient = request(client, "GET", identity, "/me", tokens["patient"]["access_token"])[
                "subject_id"
            ]
            clinic = request(
                client,
                "POST",
                tenant,
                "/clinics",
                admin,
                status=201,
                json={
                    "slug": "r04-" + str(uuid4()),
                    "name": "R04 synthetic clinic",
                    "branding": {
                        "primary_color": "#156B63",
                        "logo_url": None,
                        "description": "R04 integration verification",
                    },
                    "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
                },
            )["tenant_id"]
            request(
                client,
                "POST",
                tenant,
                f"/clinics/{clinic}/review",
                platform,
                json={"decision": "approve"},
            )
            request(
                client,
                "POST",
                identity,
                f"/clinics/{clinic}/memberships",
                admin,
                status=201,
                json={"email": "doctor@example.test", "roles": ["doctor"]},
            )
            request(
                client,
                "PUT",
                fulfilment,
                f"/clinics/{clinic}/catalogue/{medication}",
                admin,
                status=201,
                json=medicine,
            )
            start = datetime.now(timezone.utc) + timedelta(days=100)
            params = dict(
                slot=slot,
                appointment=appointment,
                tenant=clinic,
                doctor=doctor,
                patient=patient,
                start=start,
                end=start + timedelta(minutes=30),
            )
            with scheduling.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO scheduling.availability_slots "
                        "(slot_id,tenant_id,doctor_id,starts_at,ends_at) "
                        "VALUES (:slot,:tenant,:doctor,:start,:end)"
                    ),
                    params,
                )
                connection.execute(
                    text(
                        "INSERT INTO scheduling.appointments "
                        "(appointment_id,tenant_id,doctor_id,patient_id,slot_id,starts_at,"
                        "ends_at,status,consultation_price_minor,payment_resolution) VALUES "
                        "(:appointment,:tenant,:doctor,:patient,:slot,:start,:end,'in_progress',"
                        "2500,'confirmed')"
                    ),
                    params,
                )
            context = dict(
                tokens=tokens,
                tenant=clinic,
                patient=patient,
                web=web,
                appointment=str(appointment),
                medication=str(medication),
            )
            for phase in ("write", "completed"):
                if phase == "completed":
                    with scheduling.begin() as connection:
                        connection.execute(
                            text(
                                "UPDATE scheduling.appointments SET status='completed' "
                                "WHERE appointment_id=:id"
                            ),
                            {"id": appointment},
                        )
                subprocess.run(
                    [
                        "node",
                        str(ROOT / "apps/web/node_modules/tsx/dist/cli.mjs"),
                        "--tsconfig",
                        str(ROOT / "apps/web/tsconfig.json"),
                        str(ROOT / "dev/check_records_frontend.mts"),
                    ],
                    cwd=ROOT,
                    env={
                        **os.environ,
                        "R04_CONTEXT": json.dumps({**context, "phase": phase}),
                    },
                    check=True,
                )
            with records.connect() as connection:
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM clinical_records.read_audits "
                            "WHERE appointment_id=:id"
                        ),
                        {"id": appointment},
                    )
                    >= 4
                )
            print("PASS: clinical read audits persisted; real catalogue adapter used.")
        finally:
            with records.begin() as connection:
                prescriptions = connection.scalars(
                    text(
                        "SELECT prescription_id FROM clinical_records.prescriptions "
                        "WHERE appointment_id=:id"
                    ),
                    {"id": appointment},
                ).all()
                for prescription in prescriptions:
                    event_id = uuid5(
                        NAMESPACE_URL,
                        "telelink:prescription_issued.v1:" + str(prescription),
                    )
                    connection.execute(
                        text("DELETE FROM clinical_records.event_outbox WHERE event_id=:id"),
                        {"id": event_id},
                    )
                connection.execute(
                    text(
                        "DELETE FROM clinical_records.prescription_items WHERE prescription_id IN "
                        "(SELECT prescription_id FROM clinical_records.prescriptions "
                        "WHERE appointment_id=:id)"
                    ),
                    {"id": appointment},
                )
                for table in ("read_audits", "notes", "prescriptions"):
                    connection.execute(
                        text(f"DELETE FROM clinical_records.{table} WHERE appointment_id=:id"),
                        {"id": appointment},
                    )
            with scheduling.begin() as connection:
                connection.execute(
                    text("DELETE FROM scheduling.appointments WHERE appointment_id=:id"),
                    {"id": appointment},
                )
                connection.execute(
                    text("DELETE FROM scheduling.availability_slots WHERE slot_id=:id"),
                    {"id": slot},
                )
            if clinic:
                request(
                    client,
                    "PUT",
                    fulfilment,
                    f"/clinics/{clinic}/catalogue/{medication}",
                    tokens["clinic"]["access_token"],
                    json={**medicine, "active": False},
                )
                if doctor:
                    request(
                        client,
                        "DELETE",
                        identity,
                        f"/clinics/{clinic}/memberships/{doctor}",
                        tokens["clinic"]["access_token"],
                        status=204,
                    )
                request(
                    client,
                    "POST",
                    tenant,
                    f"/clinics/{clinic}/review",
                    tokens["platform"]["access_token"],
                    json={"decision": "suspend", "reason": "R04 synthetic cleanup"},
                )
            for token in tokens.values():
                cognito(
                    client,
                    "RevokeToken",
                    ClientId=client_id,
                    Token=token["refresh_token"],
                )
            scheduling.dispose()
            records.dispose()
            print("R04 synthetic data cleanup completed.")


if __name__ == "__main__":
    main()
