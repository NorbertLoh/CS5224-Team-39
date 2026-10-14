"""S03 real Floci/HTTP/PostgreSQL/Redis check; creates only synthetic new records.

Requires the three local services, S03_COGNITO_CLIENT_ID, S03_DATABASE_URL and
S03_REDIS_URL. Retains clinic/appointment history; never resets a schema or Redis DB.
"""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import redis
from check_scheduling_integration import IDENTITY, SCHEDULING, TENANT, request
from floci.check_auth import cognito, login
from sqlalchemy import text
from telelink_common.database import create_postgres_engine


def main():
    client_id = os.environ["S03_COGNITO_CLIENT_ID"]
    database_url, redis_url = os.environ["S03_DATABASE_URL"], os.environ["S03_REDIS_URL"]
    engine = create_postgres_engine(database_url)
    cache = redis.Redis.from_url(redis_url, decode_responses=True)
    tokens, clinic_id, doctor_id = {}, None, None
    with httpx.Client(timeout=15, trust_env=False) as client:
        try:
            for role in ("clinic", "doctor", "patient", "platform"):
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
            admin, doctor, patient, platform = [
                tokens[role]["access_token"] for role in ("clinic", "doctor", "patient", "platform")
            ]
            doctor_id = request(client, "GET", IDENTITY, "/me", doctor)["subject_id"]
            clinic = request(
                client,
                "POST",
                TENANT,
                "/clinics",
                admin,
                status=201,
                json={
                    "slug": "s03-" + str(uuid4()),
                    "name": "S03 synthetic clinic",
                    "branding": {
                        "primary_color": "#156B63",
                        "logo_url": None,
                        "description": "Synthetic hold integration.",
                    },
                    "consultation_price": {"amount_minor": 3210, "currency": "SGD"},
                },
            )
            clinic_id = clinic["tenant_id"]
            request(
                client,
                "POST",
                TENANT,
                f"/clinics/{clinic_id}/review",
                platform,
                json={"decision": "approve"},
            )
            request(
                client,
                "POST",
                IDENTITY,
                f"/clinics/{clinic_id}/memberships",
                admin,
                status=201,
                json={"email": "doctor@example.test", "roles": ["doctor"]},
            )

            def create_slot(start):
                return request(
                    client,
                    "POST",
                    SCHEDULING,
                    f"/clinics/{clinic_id}/slots",
                    doctor,
                    status=201,
                    json={
                        "starts_at": start.isoformat(),
                        "ends_at": (start + timedelta(minutes=30)).isoformat(),
                    },
                )

            # Prior runs retain longer holds for audit inspection. Choose a new
            # interval beyond this doctor's existing availability, across clinics.
            with engine.connect() as connection:
                latest = connection.scalar(
                    text("""
                    SELECT max(ends_at) FROM scheduling.availability_slots
                    WHERE doctor_id=:doctor AND withdrawn_at IS NULL
                """),
                    {"doctor": doctor_id},
                )
            start = datetime.now(timezone.utc) + timedelta(days=3)
            if latest is not None:
                start = max(start, latest + timedelta(hours=1))
            slot = create_slot(start)
            body = {"tenant_id": clinic_id, "slot_id": slot["slot_id"]}
            barrier = Barrier(4)

            def reserve(_):
                barrier.wait(timeout=10)
                return client.post(
                    SCHEDULING + "/appointments",
                    json=body,
                    headers={"Authorization": "Bearer " + patient},
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                responses = list(executor.map(reserve, range(4)))
            assert sorted(response.status_code for response in responses) == [201, 409, 409, 409]
            winner = next(response.json() for response in responses if response.status_code == 201)
            assert winner["consultation_price"]["amount_minor"] == 3210
            key = "telelink:scheduling:hold:" + slot["slot_id"]
            assert cache.get(key) == winner["appointment_id"] and 0 < cache.pttl(key) <= 600_000
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text("""
                    SELECT count(*) FROM scheduling.appointments
                    WHERE slot_id=:slot AND status IN
                        ('held','pending_payment','confirmed','in_progress')
                """),
                        {"slot": slot["slot_id"]},
                    )
                    == 1
                )
            request(client, "DELETE", SCHEDULING, "/slots/" + slot["slot_id"], doctor, status=409)
            for actor in (doctor, admin, platform):
                identity = request(client, "GET", IDENTITY, "/me", actor)
                # Real identities may have patient and staff roles together.
                expected = 409 if "patient" in identity["global_roles"] else 403
                request(
                    client, "POST", SCHEDULING, "/appointments", actor, status=expected, json=body
                )
            # Losing Redis state must not allocate another PostgreSQL reservation.
            cache.delete(key)
            request(client, "POST", SCHEDULING, "/appointments", patient, status=409, json=body)
            soon = create_slot(datetime.now(timezone.utc) + timedelta(seconds=8))
            short = request(
                client,
                "POST",
                SCHEDULING,
                "/appointments",
                patient,
                status=201,
                json={"tenant_id": clinic_id, "slot_id": soon["slot_id"]},
            )
            assert short["hold_expires_at"] == short["starts_at"]
            short_key = "telelink:scheduling:hold:" + soon["slot_id"]
            assert cache.get(short_key) == short["appointment_id"]
            until = time.monotonic() + 12
            while cache.get(short_key) is not None and time.monotonic() < until:
                time.sleep(0.2)
            assert cache.get(short_key) is None
            worker_env = dict(
                os.environ, SERVICE_DATABASE_URL=database_url, SERVICE_REDIS_URL=redis_url
            )
            subprocess.run(
                [sys.executable, "-m", "app.expire_holds", "--once"],
                cwd=Path(__file__).resolve().parents[1] / "services/scheduling",
                env=worker_env,
                check=True,
            )
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text("""
                    SELECT status FROM scheduling.appointments WHERE appointment_id=:id
                """),
                        {"id": short["appointment_id"]},
                    )
                    == "expired"
                )
            request(client, "DELETE", SCHEDULING, "/slots/" + soon["slot_id"], doctor, status=204)
            print("S03 real Floci/three-service/PostgreSQL/Redis hold and expiry checks passed.")
        finally:
            try:
                if clinic_id is not None and doctor_id is not None:
                    request(
                        client,
                        "DELETE",
                        IDENTITY,
                        f"/clinics/{clinic_id}/memberships/{doctor_id}",
                        tokens["clinic"]["access_token"],
                        status=204,
                    )
                    request(
                        client,
                        "POST",
                        TENANT,
                        f"/clinics/{clinic_id}/review",
                        tokens["platform"]["access_token"],
                        json={"decision": "suspend", "reason": "Synthetic S03 check complete"},
                    )
            finally:
                for token in tokens.values():
                    cognito(client, "RevokeToken", ClientId=client_id, Token=token["refresh_token"])
                cache.close()
                engine.dispose()


if __name__ == "__main__":
    main()
