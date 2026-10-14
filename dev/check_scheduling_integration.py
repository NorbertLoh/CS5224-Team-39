"""S02 real local HTTP check with four Floci accounts and three running services.

Creates two synthetic clinics and future slots, then withdraws slots, revokes the
new memberships and suspends clinics. Never resets schemas or edits existing clinics.
Requires identity:8001, tenant:8002 and scheduling:8003 with matching service keys.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from floci.check_auth import cognito, login

IDENTITY = "http://127.0.0.1:8001"
TENANT = "http://127.0.0.1:8002"
SCHEDULING = "http://127.0.0.1:8003"


def request(client, method, base, path, token=None, status=200, **kwargs):
    headers = {"Authorization": "Bearer " + token} if token else {}
    response = client.request(method, base + path, headers=headers, **kwargs)
    assert response.status_code == status, (
        f"{method} {path}: expected {status}, got {response.status_code}"
    )
    return response.json() if response.content else None


def main():
    client_id = os.environ["S02_COGNITO_CLIENT_ID"]
    tokens, clinics, slots = {}, [], []
    with httpx.Client(timeout=15, trust_env=False) as client:
        try:
            for role in ("clinic", "doctor", "patient", "platform"):
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
            admin, doctor, patient, platform = [
                tokens[role]["access_token"] for role in ("clinic", "doctor", "patient", "platform")
            ]
            doctor_id = request(client, "GET", IDENTITY, "/me", doctor)["subject_id"]
            for _ in range(2):
                clinic = request(
                    client,
                    "POST",
                    TENANT,
                    "/clinics",
                    admin,
                    status=201,
                    json={
                        "slug": "s02-" + str(uuid4()),
                        "name": "S02 synthetic clinic",
                        "branding": {
                            "primary_color": "#156B63",
                            "logo_url": None,
                            "description": "Synthetic scheduling HTTP verification.",
                        },
                        "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
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
            tenant_a, tenant_b = clinics
            for tenant_id in clinics:
                request(
                    client,
                    "POST",
                    IDENTITY,
                    f"/clinics/{tenant_id}/memberships",
                    admin,
                    status=201,
                    json={"email": "doctor@example.test", "roles": ["doctor"]},
                )
            start = datetime.now(timezone.utc) + timedelta(days=2)
            body = {
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
            }
            path = f"/clinics/{tenant_a}/slots"
            slot = request(client, "POST", SCHEDULING, path, doctor, status=201, json=body)
            slots.append(slot["slot_id"])
            assert slot["doctor_id"] == doctor_id
            request(client, "POST", SCHEDULING, path, patient, status=404, json=body)
            request(client, "POST", SCHEDULING, path, admin, status=404, json=body)
            request(client, "POST", SCHEDULING, path, platform, status=404, json=body)
            request(client, "POST", SCHEDULING, path, status=401, json=body)
            request(
                client,
                "POST",
                SCHEDULING,
                f"/clinics/{tenant_b}/slots",
                doctor,
                status=409,
                json=body,
            )
            params = {"from": start.isoformat(), "to": (start + timedelta(days=1)).isoformat()}
            listed = request(client, "GET", SCHEDULING, path, params=params)
            assert listed["items"][0]["slot_id"] == slot["slot_id"]
            assert listed["items"][0]["availability"] == "available"
            request(
                client,
                "PATCH",
                TENANT,
                f"/clinics/{tenant_a}",
                admin,
                json={"consultation_price": {"amount_minor": 3210, "currency": "SGD"}},
            )
            listed = request(client, "GET", SCHEDULING, path, params=params)
            assert listed["items"][0]["consultation_price"]["amount_minor"] == 3210
            request(client, "DELETE", SCHEDULING, "/slots/" + slot["slot_id"], patient, status=404)
            request(
                client,
                "DELETE",
                IDENTITY,
                f"/clinics/{tenant_a}/memberships/{doctor_id}",
                admin,
                status=204,
            )
            assert request(client, "GET", SCHEDULING, path, params=params)["items"] == []
            request(client, "DELETE", SCHEDULING, "/slots/" + slot["slot_id"], doctor, status=404)
            request(
                client,
                "PUT",
                IDENTITY,
                f"/clinics/{tenant_a}/memberships/{doctor_id}",
                admin,
                json={"roles": ["doctor"]},
            )
            request(client, "DELETE", SCHEDULING, "/slots/" + slot["slot_id"], doctor, status=204)
            slots.remove(slot["slot_id"])
            assert request(client, "GET", SCHEDULING, path, params=params)["items"] == []
            request(
                client,
                "POST",
                TENANT,
                f"/clinics/{tenant_a}/review",
                platform,
                json={"decision": "suspend", "reason": "Synthetic S02 gate check"},
            )
            request(client, "GET", SCHEDULING, path, params=params, status=404)
            request(client, "POST", SCHEDULING, path, doctor, json=body, status=409)
            print("S02 real Floci/identity/tenant/scheduling HTTP checks passed.")
        finally:
            # Cleanup affects only records created by this run. Keep clinic and
            # slot history for inspection; revoke all obtained refresh tokens.
            if "doctor" in tokens and "clinic" in tokens:
                doctor = tokens["doctor"]["access_token"]
                admin = tokens["clinic"]["access_token"]
                doctor_id = request(client, "GET", IDENTITY, "/me", doctor)["subject_id"]
                for slot_id in slots:
                    request(client, "DELETE", SCHEDULING, "/slots/" + slot_id, doctor, status=204)
                for tenant_id in clinics:
                    request(
                        client,
                        "DELETE",
                        IDENTITY,
                        f"/clinics/{tenant_id}/memberships/{doctor_id}",
                        admin,
                        status=204,
                    )
            if "platform" in tokens:
                for tenant_id in clinics:
                    request(
                        client,
                        "POST",
                        TENANT,
                        f"/clinics/{tenant_id}/review",
                        tokens["platform"]["access_token"],
                        json={"decision": "suspend", "reason": "Synthetic S02 cleanup"},
                    )
            for token in tokens.values():
                cognito(client, "RevokeToken", ClientId=client_id, Token=token["refresh_token"])


if __name__ == "__main__":
    main()
