"""Add upcoming availability through local APIs without resetting demo data."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values


def candidates(now, hours):
    # Stable half-hour boundaries make repeats safe and avoid shifting overlaps.
    start = now.replace(second=0, microsecond=0) + timedelta(
        minutes=3 if now.second or now.microsecond else 2
    )
    start += timedelta(minutes=(-start.minute) % 30)
    end = now + timedelta(hours=hours)
    while start + timedelta(minutes=30) <= end:
        yield start
        start += timedelta(minutes=30)


def generate(root, slug, hours, client):
    for service in ("identity", "tenant", "scheduling"):
        if (
            dotenv_values(root / f"services/{service}/.env").get("SERVICE_ENVIRONMENT")
            != "local"
        ):
            raise ValueError(
                "Only explicitly local service environments are supported."
            )
    identity = dotenv_values(root / "services/identity/.env")
    issuer = identity.get("SERVICE_AUTH_ISSUER", "")
    if not issuer.startswith(("http://localhost:4566/", "http://127.0.0.1:4566/")):
        raise ValueError("Only the local Floci identity issuer is supported.")
    auth = client.post(
        "http://127.0.0.1:4566/",
        headers={
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "Content-Type": "application/x-amz-json-1.1",
        },
        json={
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": identity["SERVICE_AUTH_CLIENT_ID"],
            "AuthParameters": {
                "USERNAME": "doctor@example.test",
                "PASSWORD": "LocalDemo123!",
            },
        },
    )
    if auth.status_code != 200:
        raise ValueError(
            "Demo doctor sign-in failed. Seed the local demo accounts first."
        )
    headers = {
        "Authorization": "Bearer " + auth.json()["AuthenticationResult"]["AccessToken"]
    }
    clinics = client.get(f"http://127.0.0.1:8002/clinics/by-slug/{slug}")
    if clinics.status_code != 200:
        raise ValueError("An active demo clinic is required.")
    clinic = clinics.json()
    tenant = clinic["tenant_id"]
    me = client.get("http://127.0.0.1:8001/me", headers=headers)
    if me.status_code != 200 or not any(
        item["tenant_id"] == tenant
        and item["status"] == "active"
        and "doctor" in item["roles"]
        for item in me.json()["memberships"]
    ):
        raise ValueError(
            "doctor@example.test must have active doctor membership in this clinic."
        )
    created, skipped = [], 0
    for start in candidates(datetime.now(timezone.utc), hours):
        response = client.post(
            f"http://127.0.0.1:8003/clinics/{tenant}/slots",
            headers=headers,
            json={
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
            },
        )
        if (
            response.status_code == 409
            and response.json().get("error", {}).get("code") == "slot_overlap"
        ):
            skipped += 1
        elif response.status_code == 201:
            created.append(response.json()["starts_at"])
        else:
            raise ValueError(
                f"Slot creation failed (HTTP {response.status_code}); existing data retained."
            )
    return {
        "clinic": clinic["name"],
        "slug": slug,
        "doctor": "doctor@example.test",
        "created_starts_at_utc": created,
        "skipped_overlaps": skipped,
        "horizon_hours": hours,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--clinic-slug", default="local-clinic", choices=None)
    parser.add_argument(
        "--hours", type=int, choices=range(1, 25), default=6, metavar="1-24"
    )
    args = parser.parse_args()
    if not args.clinic_slug or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.clinic_slug
    ):
        parser.error("Use a lowercase clinic slug with letters, digits and hyphens.")
    try:
        with httpx.Client(
            timeout=30, trust_env=False, follow_redirects=False
        ) as client:
            print(
                json.dumps(
                    generate(args.root.resolve(), args.clinic_slug, args.hours, client),
                    indent=2,
                )
            )
    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
        parser.exit(
            1, f"{error if isinstance(error, ValueError) else type(error).__name__}\n"
        )


if __name__ == "__main__":
    main()
