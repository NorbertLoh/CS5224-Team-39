"""Q02 real local booking contention and natural expiry; allow about ten minutes.

Uses patient@example.test and clinic@example.test (both have the patient role).
Creates one new slot, cancels its remaining hold and withdraws it through APIs.
PostgreSQL and Redis access is read-only. No payment or timestamp is fabricated.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import psycopg
import redis
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dev"))
from floci.check_auth import cognito, login  # noqa: E402

IDENTITY = "http://127.0.0.1:8001"
SCHEDULING = "http://127.0.0.1:8003"


def cleanup(request, http, client_id, tokens, appointments, slot):
    errors = []
    for actor, appointment_id in appointments:
        try:
            path = "/appointments/" + appointment_id
            current = request("GET", SCHEDULING, path, actor)
            if current["status"] in {"held", "pending_payment"}:
                response = http.post(
                    SCHEDULING + path + "/cancel",
                    headers={"Authorization": "Bearer " + tokens[actor]["access_token"]},
                    json={"reason": "Synthetic Q02 verification complete"},
                )
                if response.status_code == 409:
                    current = request("GET", SCHEDULING, path, actor)
                    if current["status"] != "expired":
                        response.raise_for_status()
                else:
                    response.raise_for_status()
        except Exception as exc:
            errors.append(f"appointment {appointment_id}: {type(exc).__name__}")
    if slot is not None:
        try:
            request("DELETE", SCHEDULING, "/slots/" + slot["slot_id"], "doctor", expected=204)
        except Exception as exc:
            errors.append(f"slot {slot['slot_id']}: {type(exc).__name__}")
    for actor, token in tokens.items():
        try:
            result = cognito(http, "RevokeToken", ClientId=client_id, Token=token["refresh_token"])
            if result.status_code != 200:
                raise RuntimeError("RevokeToken failed")
        except Exception as exc:
            errors.append(f"token {actor}: {type(exc).__name__}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    args = parser.parse_args()
    identity = dotenv_values(args.config_root / "services/identity/.env")
    settings = dotenv_values(args.config_root / "services/scheduling/.env")
    if not identity["SERVICE_AUTH_ISSUER"].startswith("http://localhost:4566/"):
        parser.error("Only the documented local Floci configuration is supported")
    database_url = make_url(settings["SERVICE_DATABASE_URL"])
    if database_url.host not in {"localhost", "127.0.0.1"} or database_url.port != 55411:
        parser.error("Use the persistent local development database on port 55411")
    redis_url = make_url(settings["SERVICE_REDIS_URL"])
    if redis_url.host not in {"localhost", "127.0.0.1"}:
        parser.error("Only local Redis is supported")
    report = {
        "run_id": uuid4().hex,
        "tenant_id": str(args.tenant_id),
        "checks": [],
        "complete": False,
    }
    report_file = args.config_root / ".local/q02" / (report["run_id"] + ".json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    tokens, appointments = {}, []
    slot = None
    client_id = identity["SERVICE_AUTH_CLIENT_ID"]

    def save():
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def check(name, passed):
        report["checks"].append({"name": name, "passed": bool(passed)})
        save()
        print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
        if not passed:
            raise AssertionError(name)

    print(f"Evidence: {report_file}", flush=True)
    save()
    with (
        httpx.Client(timeout=20, trust_env=False) as http,
        psycopg.connect(
            database_url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True,
            options="-c default_transaction_read_only=on",
        ) as db,
        redis.Redis.from_url(settings["SERVICE_REDIS_URL"], decode_responses=True) as cache,
    ):

        def request(method, base, path, actor=None, expected=200, **kwargs):
            headers = {"Authorization": "Bearer " + tokens[actor]["access_token"]} if actor else {}
            response = http.request(method, base + path, headers=headers, **kwargs)
            if response.status_code != expected:
                raise AssertionError(
                    f"{method} {path}: expected {expected}, got {response.status_code}"
                )
            return response.json() if response.content else None

        def active_count():
            return db.execute(
                "SELECT count(*) FROM scheduling.appointments WHERE slot_id=%s "
                "AND status IN ('held','pending_payment','confirmed','in_progress')",
                (slot["slot_id"],),
            ).fetchone()[0]

        try:
            people = {}
            for actor in ("doctor", "patient", "clinic"):
                http.cookies.clear()
                tokens[actor] = login(http, client_id, username=f"{actor}@example.test")
                people[actor] = request("GET", IDENTITY, "/me", actor)
            check(
                "two distinct authenticated patient identities",
                people["patient"]["subject_id"] != people["clinic"]["subject_id"]
                and all("patient" in people[a]["global_roles"] for a in ("patient", "clinic")),
            )
            latest = db.execute(
                "SELECT max(ends_at) FROM scheduling.availability_slots "
                "WHERE doctor_id=%s AND withdrawn_at IS NULL",
                (people["doctor"]["subject_id"],),
            ).fetchone()[0]
            start = datetime.now(timezone.utc) + timedelta(days=1)
            if latest is not None:
                start = max(start, latest + timedelta(hours=1))
            slot = request(
                "POST",
                SCHEDULING,
                f"/clinics/{args.tenant_id}/slots",
                "doctor",
                expected=201,
                json={
                    "starts_at": start.isoformat(),
                    "ends_at": (start + timedelta(minutes=30)).isoformat(),
                },
            )
            report["slot_id"] = slot["slot_id"]
            save()
            body = {"tenant_id": str(args.tenant_id), "slot_id": slot["slot_id"]}
            barrier = Barrier(2)

            def reserve(actor):
                barrier.wait(timeout=10)
                response = http.post(
                    SCHEDULING + "/appointments",
                    json=body,
                    headers={"Authorization": "Bearer " + tokens[actor]["access_token"]},
                )
                return actor, response

            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(reserve, ("patient", "clinic")))
            report["race_statuses"] = {actor: response.status_code for actor, response in results}
            for actor, response in results:
                if response.status_code == 201:
                    appointments.append((actor, response.json()["appointment_id"]))
            check(
                "competing requests return exactly one 201 and one 409",
                sorted(report["race_statuses"].values()) == [201, 409],
            )
            winner, response = next(pair for pair in results if pair[1].status_code == 201)
            loser = "clinic" if winner == "patient" else "patient"
            original = response.json()
            report["original_appointment_id"] = original["appointment_id"]
            report["hold_expires_at"] = original["hold_expires_at"]
            check("exactly one persisted active reservation", active_count() == 1)
            hold_key = "telelink:scheduling:hold:" + slot["slot_id"]
            check(
                "Redis mirrors the winning reservation",
                cache.get(hold_key) == original["appointment_id"],
            )
            request("POST", SCHEDULING, "/appointments", winner, expected=409, json=body)
            repeated = request(
                "GET", SCHEDULING, "/appointments/" + original["appointment_id"], winner
            )
            check(
                "retry does not extend the original server deadline",
                repeated["hold_expires_at"] == original["hold_expires_at"],
            )
            request("DELETE", SCHEDULING, "/slots/" + slot["slot_id"], "doctor", expected=409)
            check("reserved capacity cannot be withdrawn", active_count() == 1)
            deadline = datetime.fromisoformat(original["hold_expires_at"].replace("Z", "+00:00"))
            limit = time.monotonic() + 630
            while True:
                remaining = (
                    deadline - db.execute("SELECT clock_timestamp()").fetchone()[0]
                ).total_seconds()
                if remaining <= 0:
                    break
                if time.monotonic() > limit:
                    raise TimeoutError(
                        "The original server deadline did not elapse within 630 seconds"
                    )
                print(
                    f"Waiting for the unchanged server deadline: {remaining:.0f}s remaining",
                    flush=True,
                )
                time.sleep(min(30, remaining + 0.1))
            replacement = request(
                "POST", SCHEDULING, "/appointments", loser, expected=201, json=body
            )
            appointments.append((loser, replacement["appointment_id"]))
            report["replacement_appointment_id"] = replacement["appointment_id"]
            old_status = db.execute(
                "SELECT status FROM scheduling.appointments WHERE appointment_id=%s",
                (original["appointment_id"],),
            ).fetchone()[0]
            check(
                "natural expiry persists before another patient reallocates the slot",
                old_status == "expired",
            )
            check(
                "replacement belongs to the other patient",
                replacement["patient_id"] == people[loser]["subject_id"],
            )
            check("reallocation still leaves exactly one active reservation", active_count() == 1)
            check(
                "Redis now mirrors the replacement",
                cache.get(hold_key) == replacement["appointment_id"],
            )
            report["complete"] = True
        finally:
            verification_failed = sys.exc_info()[0] is not None
            errors = cleanup(request, http, client_id, tokens, appointments, slot)
            report["cleanup_errors"] = errors
            report["cleanup_complete"] = not errors
            report["complete"] = report["complete"] and not errors
            try:
                save()
            except OSError:
                if not verification_failed:
                    raise
                print("Cleanup report could not be saved", file=sys.stderr)
            if errors:
                print("Cleanup incomplete: " + "; ".join(errors), file=sys.stderr)
                if not verification_failed:
                    raise RuntimeError("Cleanup incomplete; see the evidence report")
    print(
        "Q02 race/expiry checks passed; provider limits are documented separately.",
        flush=True,
    )


if __name__ == "__main__":
    main()
