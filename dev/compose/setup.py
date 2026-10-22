"""Explicit local-only configuration, schema provisioning, seeding and smoke checks."""

import argparse
import json
import os
import secrets
import shutil
import sys
from pathlib import Path, PureWindowsPath
from uuid import uuid4

import boto3
import httpx
import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path("/workspace")
STATE = Path("/state")
SERVICES = (
    "identity",
    "tenant",
    "scheduling",
    "consultation",
    "clinical_records",
    "fulfilment",
    "document",
    "billing",
    "notification",
)
AWS = {"endpoint_url": "http://floci:4566", "region_name": "ap-southeast-1"}


def aws(name):
    return boto3.client(name, **AWS)


def cognito_context():
    client = aws("cognito-idp")
    pools = [
        p
        for p in client.list_user_pools(MaxResults=60)["UserPools"]
        if p["Name"] == "telelink-local"
    ]
    if len(pools) != 1:
        raise RuntimeError("Run the Floci bootstrap first; expected one local pool")
    pool = pools[0]["Id"]
    clients = [
        c
        for c in client.list_user_pool_clients(UserPoolId=pool, MaxResults=60)[
            "UserPoolClients"
        ]
        if c["ClientName"] == "telelink-web"
    ]
    if len(clients) != 1:
        raise RuntimeError("Expected one public local SPA client")
    return client, pool, clients[0]["ClientId"]


def write_env(name, values):
    # Compose reads these files in raw format: JSON and provider keys stay literal.
    for value in values.values():
        if value is not None and ("\n" in str(value) or "\r" in str(value)):
            raise ValueError("Multiline environment values are unsupported")
    (STATE / name).write_text(
        "".join(f"{k}={v}\n" for k, v in values.items() if v is not None),
        encoding="utf-8",
    )


def configure():
    STATE.mkdir(parents=True, exist_ok=True)
    _, pool, client_id = cognito_context()
    key_path = STATE / "keys.json"
    keys = json.loads(key_path.read_text()) if key_path.exists() else {}
    source = {s: dict(dotenv_values(ROOT / "services" / s / ".env")) for s in SERVICES}
    configs = {s: {} for s in SERVICES}

    def key(name, candidates=()):
        if name not in keys:
            keys[name] = next(
                (source[s].get(k) for s, k in candidates if source[s].get(k)),
                secrets.token_urlsafe(48),
            )
        return keys[name]

    def pair(a, ak, b, bk):
        value = key(f"{a}:{ak}:{b}", [(a, ak), (b, bk)])
        configs[a][ak] = configs[b][bk] = value

    pair("identity", "SERVICE_TENANT_SECRET", "tenant", "SERVICE_TENANT_SECRET")
    pair("identity", "SERVICE_IDENTITY_SECRET", "tenant", "SERVICE_IDENTITY_SECRET")
    pair(
        "scheduling", "SERVICE_SCHEDULING_SECRET", "tenant", "SERVICE_SCHEDULING_SECRET"
    )
    pair("scheduling", "SERVICE_BILLING_SECRET", "billing", "SERVICE_SCHEDULING_SECRET")
    pair("billing", "SERVICE_TENANT_SECRET", "tenant", "SERVICE_BILLING_SECRET")
    for peer, setting in [
        ("identity", "IDENTITY"),
        ("scheduling", "SCHEDULING"),
        ("billing", "BILLING"),
        ("clinical_records", "RECORDS"),
    ]:
        pair(
            "consultation",
            f"SERVICE_{setting}_SECRET",
            peer,
            "SERVICE_CONSULTATION_SECRET",
        )
    pair(
        "clinical_records",
        "SERVICE_DOCUMENT_SECRET",
        "document",
        "SERVICE_RECORDS_SECRET",
    )
    pair(
        "clinical_records",
        "SERVICE_IDENTITY_DOCUMENT_SECRET",
        "identity",
        "SERVICE_RECORDS_SECRET",
    )
    pair(
        "clinical_records",
        "SERVICE_TENANT_DOCUMENT_SECRET",
        "tenant",
        "SERVICE_RECORDS_SECRET",
    )
    pair(
        "clinical_records",
        "SERVICE_FULFILMENT_SECRET",
        "fulfilment",
        "SERVICE_RECORDS_SECRET",
    )
    pair("fulfilment", "SERVICE_BILLING_SECRET", "billing", "SERVICE_FULFILMENT_SECRET")
    for peer, setting in [
        ("identity", "IDENTITY"),
        ("scheduling", "SCHEDULING"),
        ("document", "DOCUMENT"),
        ("fulfilment", "FULFILMENT"),
    ]:
        pair(
            "notification",
            f"SERVICE_{setting}_SECRET",
            peer,
            "SERVICE_NOTIFICATION_SECRET",
        )

    for name, config in configs.items():
        config.update(
            SERVICE_ENVIRONMENT="local",
            SERVICE_HOST="0.0.0.0",
            SERVICE_PORT=8000,
            SERVICE_DATABASE_URL=f"postgresql+psycopg://{name}:local-demo-only@postgres:5432/telelink",
            SERVICE_AUTH_ISSUER=f"http://localhost:4566/{pool}",
            SERVICE_AUTH_JWKS_URL=f"http://floci:4566/{pool}/.well-known/jwks.json",
            SERVICE_AUTH_CLIENT_ID=client_id,
            SERVICE_AUTH_REQUIRED_SCOPES="openid",
            SERVICE_AUTH_ALLOW_PASSWORD_TOKENS="true",
            SERVICE_IDENTITY_URL="http://identity:8000",
            SERVICE_AWS_REGION="ap-southeast-1",
            SERVICE_AWS_ENDPOINT_URL="http://floci:4566",
            SERVICE_EVENT_BUS_NAME="telelink-local",
            AWS_ACCESS_KEY_ID="test",
            AWS_SECRET_ACCESS_KEY="test",
            AWS_EC2_METADATA_DISABLED="true",
        )
        if name != "notification":
            config["SERVICE_CURSOR_SECRET"] = key(
                name + ":cursor", [(name, "SERVICE_CURSOR_SECRET")]
            )
    for name in ["identity", "scheduling", "clinical_records", "billing"]:
        configs[name]["SERVICE_TENANT_URL"] = "http://tenant:8000"
    for name in [
        "consultation",
        "clinical_records",
        "document",
        "billing",
        "notification",
    ]:
        configs[name]["SERVICE_SCHEDULING_URL"] = "http://scheduling:8000"
    for name in ["scheduling", "consultation", "fulfilment"]:
        configs[name]["SERVICE_BILLING_URL"] = "http://billing:8000"
    for name in ["consultation", "document", "fulfilment"]:
        configs[name]["SERVICE_RECORDS_URL"] = (
            "http://clinical_records:8000/api/v1/clinical-records"
        )
    for name in ["clinical_records", "billing", "notification"]:
        configs[name]["SERVICE_FULFILMENT_URL"] = "http://fulfilment:8000"
    configs["notification"].update(
        SERVICE_DOCUMENT_URL="http://document:8000",
        SERVICE_EMAIL_SENDER="notifications@telelink.test",
        SERVICE_APP_URL="https://localhost:8443",
    )
    configs["tenant"].update(
        SERVICE_LOGO_BUCKET="telelink-local-branding",
        SERVICE_LOGO_PUBLIC_BASE_URL="https://local-assets.example.test",
        SERVICE_LOGO_S3_ENDPOINT="http://floci:4566",
    )
    configs["scheduling"]["SERVICE_REDIS_URL"] = "redis://redis:6379/0"
    configs["consultation"]["SERVICE_SIGNALLING_SECRET"] = key(
        "signalling", [("consultation", "SERVICE_SIGNALLING_SECRET")]
    )
    configs["document"]["SERVICE_S3_BROWSER_ENDPOINT_URL"] = "http://localhost:4566"
    billing = configs["billing"]
    billing.update(
        SERVICE_CHECKOUT_SUCCESS_URL="https://localhost:8443/patient/checkout",
        SERVICE_CHECKOUT_CANCEL_URL="https://localhost:8443/patient/checkout",
    )
    for setting, legacy in [
        ("SERVICE_STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY"),
        ("SERVICE_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"),
    ]:
        value = source["billing"].get(setting) or source["billing"].get(legacy)
        if value:
            billing[setting] = value
    billing["SERVICE_STRIPE_DESTINATIONS"] = (
        source["billing"].get("SERVICE_STRIPE_DESTINATIONS") or "{}"
    )
    for setting, legacy in [
        ("SERVICE_LALAMOVE_API_KEY", "LALAMOVE_API_KEY"),
        ("SERVICE_LALAMOVE_API_SECRET", "LALAMOVE_API_SECRET"),
    ]:
        value = source["fulfilment"].get(setting) or source["fulfilment"].get(legacy)
        if value:
            configs["fulfilment"][setting] = value
    for setting in [
        "SERVICE_DELIVERY_LOCATIONS_PATH",
        "SERVICE_DELIVERY_CONTACTS_PATH",
    ]:
        value = source["fulfilment"].get(setting)
        if value:
            # Host Windows paths must never leak into container settings.
            parts = PureWindowsPath(value).parts
            if ".local" in parts:
                relative = Path(*parts[parts.index(".local") :])
                if ".." not in relative.parts and (ROOT / relative).is_file():
                    delivery = STATE / "delivery"
                    delivery.mkdir(exist_ok=True)
                    filename = (
                        "locations.json"
                        if setting.endswith("LOCATIONS_PATH")
                        else "contacts.json"
                    )
                    shutil.copy2(ROOT / relative, delivery / filename)
                    configs["fulfilment"][setting] = "/delivery/" + filename
    with psycopg.connect(
        host="postgres",
        dbname="telelink",
        user="postgres",
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,
    ) as db:
        for name in SERVICES:
            if not db.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)
            ).fetchone():
                db.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(name), sql.Literal("local-demo-only")
                    )
                )
            db.execute(
                sql.SQL("GRANT CONNECT ON DATABASE telelink TO {}").format(
                    sql.Identifier(name)
                )
            )
            db.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                    sql.Identifier(name), sql.Identifier(name)
                )
            )
        if (
            billing["SERVICE_STRIPE_DESTINATIONS"] == "{}"
            and source["billing"].get("STRIPE_CONNECTED_ACCOUNT_ID")
            and db.execute("SELECT to_regclass('tenant.clinics')").fetchone()[0]
        ):
            billing["SERVICE_STRIPE_DESTINATIONS"] = json.dumps(
                {
                    str(row[0]): source["billing"]["STRIPE_CONNECTED_ACCOUNT_ID"]
                    for row in db.execute(
                        "SELECT tenant_id FROM tenant.clinics WHERE status='active'"
                    )
                }
            )
    for name, config in configs.items():
        write_env(name + ".env", config)
    write_env(
        "web.env",
        {
            "VITE_USE_AWS": "false",
            "VITE_LOCAL_API_BASE_URL": "/api/v1",
            "VITE_COGNITO_CLIENT_ID": client_id,
            "VITE_COGNITO_ISSUER": f"http://localhost:4566/{pool}",
            "VITE_COGNITO_OAUTH_BASE_URL": "http://localhost:4566/cognito-idp",
            "VITE_COGNITO_API_URL": "http://localhost:4566/",
            **{
                key + "_API_TARGET": f"http://{service}:8000"
                for key, service in [
                    ("IDENTITY", "identity"),
                    ("TENANT", "tenant"),
                    ("SCHEDULING", "scheduling"),
                    ("BILLING", "billing"),
                    ("CONSULTATION", "consultation"),
                    ("RECORDS", "clinical_records"),
                    ("DOCUMENT", "document"),
                    ("FULFILMENT", "fulfilment"),
                ]
            },
        },
    )
    existing = dict(dotenv_values(STATE / "compose.env"))
    existing.update(
        SIGNALLING_SECRET=configs["consultation"]["SERVICE_SIGNALLING_SECRET"],
        STRIPE_API_KEY=billing.get("SERVICE_STRIPE_SECRET_KEY", ""),
    )
    write_env("compose.env", existing)
    key_path.write_text(json.dumps(keys), encoding="utf-8")
    print("Local configuration and service-owned schemas ready; no data reset.")
    if (
        not billing.get("SERVICE_STRIPE_SECRET_KEY")
        or billing["SERVICE_STRIPE_DESTINATIONS"] == "{}"
    ):
        print(
            "Payments need Stripe test credentials and an active clinic destination; see docs/compose-stack.md."
        )


def seed():
    cognito, pool, _ = cognito_context()
    with psycopg.connect(
        "postgresql://identity:local-demo-only@postgres/telelink"
    ) as db:
        for name, roles in [
            ("patient", ["patient"]),
            ("doctor", []),
            ("clinic", ["patient"]),
            ("platform", ["platform_admin"]),
        ]:
            attrs = {
                a["Name"]: a["Value"]
                for a in cognito.admin_get_user(
                    UserPoolId=pool, Username=f"{name}@example.test"
                )["UserAttributes"]
            }
            db.execute(
                "INSERT INTO identity.subjects (subject_id,cognito_sub,display_name,global_roles,email) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (cognito_sub) DO UPDATE SET email=EXCLUDED.email",
                (
                    uuid4(),
                    attrs["sub"],
                    f"Local {name.title()}",
                    roles,
                    attrs["email"].lower(),
                ),
            )
    s3 = aws("s3")
    if "telelink-local-branding" not in [
        b["Name"] for b in s3.list_buckets()["Buckets"]
    ]:
        s3.create_bucket(
            Bucket="telelink-local-branding",
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-1"},
        )
    s3.put_public_access_block(
        Bucket="telelink-local-branding",
        PublicAccessBlockConfiguration={
            key: True
            for key in [
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            ]
        },
    )
    ses = aws("ses")
    for email in [
        "notifications@telelink.test",
        *[
            f"{name}@example.test"
            for name in ["patient", "doctor", "clinic", "platform"]
        ],
    ]:
        ses.verify_email_identity(EmailAddress=email)
    print(
        "Four actual Cognito subjects provisioned; existing profiles and memberships preserved. Branding and local SES ready."
    )


def check():
    sys.path.insert(0, str(ROOT / "dev"))
    from floci.check_auth import login

    _, _, client_id = cognito_context()
    with httpx.Client(timeout=30, trust_env=False) as client:
        for name in SERVICES:
            if name == "notification":
                continue
            response = client.get(f"http://{name}:8000/health/ready")
            response.raise_for_status()
            print(name + ": ready", flush=True)
        client.get("http://web:5173/").raise_for_status()
        for name in ["patient", "doctor", "clinic", "platform"]:
            client.cookies.clear()
            tokens = login(
                client,
                client_id,
                oauth="http://floci:4566/cognito-idp",
                callback="https://localhost:8443/auth/callback",
                username=f"{name}@example.test",
            )
            client.get(
                "http://identity:8000/me",
                headers={"Authorization": "Bearer " + tokens["access_token"]},
            ).raise_for_status()
            print(name + ": PKCE login and profile OK", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "seed", "check"])
    globals()[parser.parse_args().action]()
