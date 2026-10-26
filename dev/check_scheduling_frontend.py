"""Exercise S07 TypeScript adapters against fixed localhost services.

Creates only new synthetic clinics. Retains appointment history, revokes this
run's doctor memberships/tokens, and suspends its clinics. Never resets schemas.
Run using services/identity/.venv/Scripts/python.exe with Vite on port 5173.
"""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
from check_scheduling_integration import IDENTITY, TENANT, request
from dotenv import dotenv_values
from floci.check_auth import cognito, login

ROOT = Path(__file__).resolve().parents[1]


def main():
    client_id = dotenv_values(ROOT / "services/identity/.env")["SERVICE_AUTH_CLIENT_ID"]
    clinics, tokens, doctor_id = [], {}, None
    with httpx.Client(timeout=20, trust_env=False) as client:
        try:
            for role in ("clinic", "doctor", "patient", "platform"):
                client.cookies.clear()
                tokens[role] = login(client, client_id, username=f"{role}@example.test")
            admin = tokens["clinic"]["access_token"]
            platform = tokens["platform"]["access_token"]
            doctor_id = request(
                client, "GET", IDENTITY, "/me", tokens["doctor"]["access_token"]
            )["subject_id"]
            for _ in range(2):
                clinic = request(
                    client,
                    "POST",
                    TENANT,
                    "/clinics",
                    admin,
                    status=201,
                    json={
                        "slug": "s07-" + str(uuid4()),
                        "name": "S07 synthetic clinic",
                        "branding": {
                            "primary_color": "#156B63",
                            "logo_url": None,
                            "description": "S07 frontend adapter verification.",
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
                    admin,
                    status=201,
                    json={"email": "doctor@example.test", "roles": ["doctor"]},
                )
            env = {
                **os.environ,
                "S07_CONTEXT": json.dumps({"tokens": tokens, "clinics": clinics}),
            }
            subprocess.run(
                [
                    "node",
                    str(ROOT / "dev/run_frontend_probe.mjs"),
                    "check_scheduling_frontend.mts",
                ],
                env=env,
                cwd=ROOT,
                check=True,
            )
        finally:
            if doctor_id and "clinic" in tokens:
                for clinic in clinics:
                    request(
                        client,
                        "DELETE",
                        IDENTITY,
                        f"/clinics/{clinic}/memberships/{doctor_id}",
                        tokens["clinic"]["access_token"],
                        status=204,
                    )
            if "platform" in tokens:
                for clinic in clinics:
                    request(
                        client,
                        "POST",
                        TENANT,
                        f"/clinics/{clinic}/review",
                        tokens["platform"]["access_token"],
                        json={"decision": "suspend", "reason": "S07 synthetic cleanup"},
                    )
            for token in tokens.values():
                cognito(
                    client,
                    "RevokeToken",
                    ClientId=client_id,
                    Token=token["refresh_token"],
                )


if __name__ == "__main__":
    main()
