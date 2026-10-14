"""S04 real local appointment API check; confirmed states are explicit SQL fixtures.

Requires local identity/tenant/scheduling services and S04_* configuration below.
Does not claim billing/payment or consultation admission integration. Creates only
new synthetic clinics/slots/appointments, preserves history and never resets schemas.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import jwt
from check_scheduling_integration import IDENTITY, SCHEDULING, TENANT, request
from floci.check_auth import cognito, login
from sqlalchemy import text
from telelink_common.database import create_postgres_engine


def main():
    client_id = os.environ["S04_COGNITO_CLIENT_ID"]
    engine = create_postgres_engine(os.environ["S04_DATABASE_URL"])
    tokens, clinics, slots, subjects = {}, [], [], {}
    with httpx.Client(timeout=15, trust_env=False) as client:
        try:
            for role in ("clinic", "doctor", "patient", "platform"):
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
                subjects[role] = request(
                    client, "GET", IDENTITY, "/me", tokens[role]["access_token"]
                )["subject_id"]
            admin, doctor, patient, platform = [
                tokens[role]["access_token"] for role in ("clinic", "doctor", "patient", "platform")
            ]
            for owner in (admin, patient):
                clinic = request(
                    client,
                    "POST",
                    TENANT,
                    "/clinics",
                    owner,
                    status=201,
                    json={
                        "slug": "s04-" + str(uuid4()),
                        "name": "S04 synthetic clinic",
                        "branding": {
                            "primary_color": "#156B63",
                            "logo_url": None,
                            "description": "Synthetic appointment verification.",
                        },
                        "consultation_price": {"amount_minor": 3210, "currency": "SGD"},
                    },
                )
                clinics.append(clinic["tenant_id"])
                request(
                    client,
                    "POST",
                    TENANT,
                    f"/clinics/{clinics[-1]}/review",
                    platform,
                    json={"decision": "approve"},
                )
                request(
                    client,
                    "POST",
                    IDENTITY,
                    f"/clinics/{clinics[-1]}/memberships",
                    owner,
                    status=201,
                    json={"email": "doctor@example.test", "roles": ["doctor"]},
                )
            tenant_a, tenant_b = clinics
            with engine.connect() as connection:
                latest = connection.scalar(
                    text("""
                    SELECT max(ends_at) FROM scheduling.availability_slots
                    WHERE doctor_id=:doctor AND withdrawn_at IS NULL
                """),
                    {"doctor": subjects["doctor"]},
                )
            future = max(
                datetime.now(timezone.utc) + timedelta(days=3),
                latest + timedelta(hours=1) if latest else datetime.now(timezone.utc),
            )

            def book(tenant_id, start):
                slot = request(
                    client,
                    "POST",
                    SCHEDULING,
                    f"/clinics/{tenant_id}/slots",
                    doctor,
                    status=201,
                    json={
                        "starts_at": start.isoformat(),
                        "ends_at": (start + timedelta(minutes=30)).isoformat(),
                    },
                )
                slots.append(slot["slot_id"])
                return request(
                    client,
                    "POST",
                    SCHEDULING,
                    "/appointments",
                    patient,
                    status=201,
                    json={"tenant_id": tenant_id, "slot_id": slot["slot_id"]},
                )

            own, foreign = book(tenant_a, future), book(tenant_b, future + timedelta(hours=1))
            path = "/appointments/" + own["appointment_id"]
            for token in (patient, doctor, admin, platform):
                result = request(client, "GET", SCHEDULING, path, token)
                assert result["appointment_id"] == own["appointment_id"]
                assert "cancellation_reason" not in result and "email" not in result
            request(client, "GET", SCHEDULING, path, status=401)
            request(
                client,
                "GET",
                SCHEDULING,
                "/appointments/" + foreign["appointment_id"],
                admin,
                status=404,
            )
            for actor in (doctor, platform):
                request(
                    client,
                    "POST",
                    SCHEDULING,
                    path + "/cancel",
                    actor,
                    status=404,
                    json={"reason": "Denied"},
                )
            page = request(
                client,
                "GET",
                SCHEDULING,
                "/appointments",
                patient,
                params={"tenant_id": tenant_a, "limit": 1},
            )
            assert [item["appointment_id"] for item in page["items"]] == [own["appointment_id"]]
            request(
                client,
                "DELETE",
                IDENTITY,
                f"/clinics/{tenant_a}/memberships/{subjects['doctor']}",
                admin,
                status=204,
            )
            request(client, "GET", SCHEDULING, path, doctor, status=404)
            request(client, "GET", SCHEDULING, path, patient)
            cancelled = request(
                client,
                "POST",
                SCHEDULING,
                path + "/cancel",
                patient,
                json={"reason": "Synthetic patient request"},
            )
            assert cancelled["status"] == "cancelled"
            repeated = request(
                client, "POST", SCHEDULING, path + "/cancel", patient, json={"reason": "Retry"}
            )
            assert repeated["updated_at"] == cancelled["updated_at"]
            with engine.connect() as connection:
                row = connection.execute(
                    text("""
                    SELECT cancellation_reason,cancelled_by_subject_id FROM scheduling.appointments
                    WHERE appointment_id=:id
                """),
                    {"id": own["appointment_id"]},
                ).one()
                assert row.cancellation_reason == "Synthetic patient request"
                assert str(row.cancelled_by_subject_id) == subjects["patient"]
            request(
                client,
                "PUT",
                IDENTITY,
                f"/clinics/{tenant_a}/memberships/{subjects['doctor']}",
                admin,
                json={"roles": ["doctor"]},
            )

            def confirmed_fixture(start):
                slot_id, appointment_id = uuid4(), uuid4()
                with engine.begin() as connection:
                    values = {
                        "slot": slot_id,
                        "id": appointment_id,
                        "tenant": tenant_a,
                        "doctor": subjects["doctor"],
                        "patient": subjects["patient"],
                        "start": start,
                        "end": start + timedelta(minutes=30),
                        "payment": uuid4(),
                    }
                    connection.execute(
                        text("""
                        INSERT INTO scheduling.availability_slots
                        (slot_id,tenant_id,doctor_id,starts_at,ends_at)
                        VALUES (:slot,:tenant,:doctor,:start,:end)
                    """),
                        values,
                    )
                    connection.execute(
                        text("""
                        INSERT INTO scheduling.appointments
                        (appointment_id,slot_id,tenant_id,patient_id,doctor_id,starts_at,ends_at,
                         status,consultation_price_minor,currency,payment_id,payment_resolution)
                        VALUES (:id,:slot,:tenant,:patient,:doctor,:start,:end,
                                'confirmed',3210,'SGD',:payment,'confirmed')
                    """),
                        values,
                    )
                slots.append(str(slot_id))
                return "/appointments/" + str(appointment_id)

            paid = confirmed_fixture(future + timedelta(hours=2))
            flagged = request(
                client,
                "POST",
                SCHEDULING,
                paid + "/cancel",
                admin,
                json={"reason": "Synthetic paid cancellation"},
            )
            assert (
                flagged["status"] == "cancelled"
                and flagged["payment_resolution"] == "refund_required"
            )

            def service_headers(caller):
                now = int(time.time())
                consultation = caller == "consultation"
                token = jwt.encode(
                    {
                        "iss": "telelink-service:" + caller,
                        "sub": caller,
                        "aud": "telelink-scheduling-consultation"
                        if consultation
                        else "telelink-scheduling-operator",
                        "iat": now,
                        "exp": now + 60,
                    },
                    os.environ[
                        "S04_CONSULTATION_SECRET" if consultation else "S04_OPERATOR_SECRET"
                    ],
                    algorithm="HS256",
                )
                return {"Authorization": "Bearer " + token}

            active = confirmed_fixture(datetime.now(timezone.utc) - timedelta(minutes=5))
            request(
                client, "POST", SCHEDULING, "/internal" + active + "/start", patient, status=401
            )
            response = client.post(
                SCHEDULING + "/internal" + active + "/start",
                headers=service_headers("consultation"),
            )
            assert response.status_code == 200 and response.json()["status"] == "in_progress"
            response = client.post(
                SCHEDULING + "/internal" + active + "/complete",
                headers=service_headers("consultation"),
            )
            assert response.status_code == 200 and response.json()["status"] == "completed"
            missed = confirmed_fixture(datetime.now(timezone.utc) - timedelta(hours=1))
            response = client.post(
                SCHEDULING + "/internal" + missed + "/no-show",
                headers=service_headers("scheduling-operator"),
            )
            assert response.status_code == 200 and response.json()["status"] == "no_show"
            request(
                client,
                "POST",
                SCHEDULING,
                "/appointments/" + foreign["appointment_id"] + "/cancel",
                patient,
                json={"reason": "Synthetic cleanup"},
            )
            # Cancellation does not require a clinic to keep accepting new bookings.
            request(
                client,
                "POST",
                TENANT,
                f"/clinics/{tenant_a}/review",
                platform,
                json={"decision": "suspend", "reason": "Synthetic read gate check"},
            )
            request(client, "GET", SCHEDULING, path, patient)
            print("S04 real Floci/three-service reads, cancellation and service actions passed.")
            print(
                "Confirmed states were explicit SQL fixtures; no payment integration was verified."
            )
        finally:
            try:
                if "doctor" in tokens:
                    for slot_id in slots:
                        # Only synthetic rows created here; keep unfinished reservations on failure.
                        client.delete(
                            SCHEDULING + "/slots/" + slot_id,
                            headers={"Authorization": "Bearer " + tokens["doctor"]["access_token"]},
                        )
                for index, tenant_id in enumerate(clinics):
                    owner = tokens["clinic" if index == 0 else "patient"]["access_token"]
                    request(
                        client,
                        "DELETE",
                        IDENTITY,
                        f"/clinics/{tenant_id}/memberships/{subjects['doctor']}",
                        owner,
                        status=204,
                    )
                    request(
                        client,
                        "POST",
                        TENANT,
                        f"/clinics/{tenant_id}/review",
                        tokens["platform"]["access_token"],
                        json={"decision": "suspend", "reason": "Synthetic S04 cleanup"},
                    )
            finally:
                for token in tokens.values():
                    cognito(client, "RevokeToken", ClientId=client_id, Token=token["refresh_token"])
                engine.dispose()


if __name__ == "__main__":
    main()
