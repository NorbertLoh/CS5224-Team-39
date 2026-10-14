"""Configure the real local clinic services; optionally create a database-backed clinic.

Requires migrated local PostgreSQL (port 55411), Floci and its Cognito bootstrap.
Run using the identity virtualenv. Never targets an AWS account.
"""

import argparse
import json
import secrets
from pathlib import Path
from uuid import uuid4

import boto3
import httpx
import psycopg
from floci.check_auth import login

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/clinic"
AWS = {
    "endpoint_url": "http://localhost:4566",
    "region_name": "ap-southeast-1",
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}


def write_new(path, values):
    if not path.exists():
        path.write_text(
            "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--create-clinic",
        action="store_true",
        help="Create and approve a local clinic through the running APIs",
    )
    args = parser.parse_args()
    cognito = boto3.client("cognito-idp", **AWS)
    pool = next(
        item["Id"]
        for item in cognito.list_user_pools(MaxResults=60)["UserPools"]
        if item["Name"] == "telelink-local"
    )
    client_id = next(
        item["ClientId"]
        for item in cognito.list_user_pool_clients(UserPoolId=pool, MaxResults=60)[
            "UserPoolClients"
        ]
        if item["ClientName"] == "telelink-web"
    )
    client = cognito.describe_user_pool_client(UserPoolId=pool, ClientId=client_id)[
        "UserPoolClient"
    ]
    callbacks = set(client.get("CallbackURLs", []))
    logouts = set(client.get("LogoutURLs", []))
    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        callbacks.add(origin + "/auth/callback")
        logouts.add(origin + "/")
    cognito.update_user_pool_client(
        UserPoolId=pool,
        ClientId=client_id,
        ClientName="telelink-web",
        SupportedIdentityProviders=["COGNITO"],
        AllowedOAuthFlowsUserPoolClient=True,
        AllowedOAuthFlows=["code"],
        AllowedOAuthScopes=["openid", "email", "profile"],
        ExplicitAuthFlows=["ALLOW_REFRESH_TOKEN_AUTH"],
        PreventUserExistenceErrors="ENABLED",
        CallbackURLs=sorted(callbacks),
        LogoutURLs=sorted(logouts),
    )
    LOCAL.mkdir(parents=True, exist_ok=True)
    key_file = LOCAL / "keys.json"
    if not key_file.exists():
        key_file.write_text(
            json.dumps(
                {
                    name: secrets.token_urlsafe(48)
                    for name in [
                        "tenant",
                        "identity",
                        "identity_cursor",
                        "tenant_cursor",
                    ]
                }
            )
        )
    keys = json.loads(key_file.read_text())
    common = {
        "SERVICE_ENVIRONMENT": "local",
        "SERVICE_AUTH_ISSUER": f"http://localhost:4566/{pool}",
        "SERVICE_AUTH_JWKS_URL": f"http://localhost:4566/{pool}/.well-known/jwks.json",
        "SERVICE_AUTH_CLIENT_ID": client_id,
        "SERVICE_AUTH_REQUIRED_SCOPES": "openid",
        "SERVICE_TENANT_SECRET": keys["tenant"],
        "SERVICE_IDENTITY_SECRET": keys["identity"],
    }
    for name in ["identity", "tenant"]:
        settings = common | {
            "SERVICE_DATABASE_URL": f"postgresql+psycopg://{name}:local-demo-only@127.0.0.1:55411/telelink",
            "SERVICE_CURSOR_SECRET": keys[f"{name}_cursor"],
        }
        if name == "identity":
            settings["SERVICE_TENANT_URL"] = "http://127.0.0.1:8002"
        else:
            settings |= {
                "SERVICE_IDENTITY_URL": "http://127.0.0.1:8001",
                "SERVICE_LOGO_BUCKET": "telelink-local-branding",
                "SERVICE_LOGO_PUBLIC_BASE_URL": "https://local-assets.example.test",
                "SERVICE_LOGO_S3_ENDPOINT": "http://localhost:4566",
            }
        write_new(ROOT / f"services/{name}/.env", settings)
    write_new(
        ROOT / "apps/web/.env",
        {
            "VITE_USE_AWS": "false",
            "VITE_LOCAL_API_BASE_URL": "/api/v1",
            "VITE_COGNITO_CLIENT_ID": client_id,
            "VITE_COGNITO_ISSUER": f"http://localhost:4566/{pool}",
            "VITE_COGNITO_OAUTH_BASE_URL": "http://localhost:4566/cognito-idp",
            "VITE_COGNITO_API_URL": "http://localhost:4566/",
        },
    )
    s3 = boto3.client("s3", **AWS)
    bucket = "telelink-local-branding"
    if bucket not in [item["Name"] for item in s3.list_buckets()["Buckets"]]:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-1"},
        )
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    # Explicit local operator provisioning, using actual Cognito subjects, never groups.
    with psycopg.connect(
        "postgresql://identity:local-demo-only@127.0.0.1:55411/telelink"
    ) as db:
        for name, roles in [
            ("patient", ["patient"]),
            ("doctor", []),
            ("clinic", ["patient"]),
            ("platform", ["platform_admin"]),
        ]:
            attributes = cognito.admin_get_user(
                UserPoolId=pool, Username=f"{name}@example.test"
            )["UserAttributes"]
            sub = next(item["Value"] for item in attributes if item["Name"] == "sub")
            email = next(
                item["Value"] for item in attributes if item["Name"] == "email"
            )
            db.execute(
                "INSERT INTO identity.subjects "
                "(subject_id, cognito_sub, display_name, global_roles, email) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (cognito_sub) DO UPDATE SET email = EXCLUDED.email",
                (uuid4(), sub, f"Local {name.title()}", roles, email.strip().lower()),
            )
    print(
        "Local configuration ready. Existing .env files and database profiles were preserved."
    )
    if args.create_clinic:
        create_clinic(client_id)


def create_clinic(client_id):
    def credential(name):
        with httpx.Client(timeout=10) as http:
            tokens = login(http, client_id, username=f"{name}@example.test")
        return {"Authorization": "Bearer " + tokens["access_token"]}

    admin = credential("clinic")
    platform = credential("platform")
    with httpx.Client(timeout=10) as http:
        response = http.get("http://127.0.0.1:8001/me", headers=admin)
        response.raise_for_status()
        if response.json()["memberships"]:
            print("Local clinic already exists; its saved profile was preserved.")
            return
        response = http.post(
            "http://127.0.0.1:8002/clinics",
            headers=admin,
            json={
                "slug": "local-clinic",
                "name": "Local Clinic",
                "branding": {
                    "primary_color": "#156B63",
                    "logo_url": None,
                    "description": "Local clinic profile.",
                },
                "consultation_price": {"amount_minor": 2500, "currency": "SGD"},
            },
        )
        response.raise_for_status()
        tenant_id = response.json()["tenant_id"]
        response = http.post(
            f"http://127.0.0.1:8002/clinics/{tenant_id}/review",
            headers=platform,
            json={"decision": "approve"},
        )
        response.raise_for_status()
        response = http.get("http://127.0.0.1:8001/me", headers=credential("doctor"))
        response.raise_for_status()
        doctor_id = response.json()["subject_id"]
        response = http.put(
            f"http://127.0.0.1:8001/clinics/{tenant_id}/memberships/{doctor_id}",
            headers=admin,
            json={"roles": ["doctor"]},
        )
        response.raise_for_status()
        print(f"Created database-backed clinic: /clinics/local-clinic (ID {tenant_id})")


if __name__ == "__main__":
    main()
