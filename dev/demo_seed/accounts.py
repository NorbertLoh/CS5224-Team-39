"""Read-only preflight or explicit accounts-only seed for the local Compose stack."""

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import boto3
import httpx
import psycopg
from dotenv import dotenv_values

ACCOUNTS = (
    ("patient@example.test", "Local Patient", ["patient"]),
    ("lohnorbert@gmail.com", "Norbert", ["patient"]),
    ("doctor@example.test", "Local Doctor", []),
    ("clinic@example.test", "Local Clinic Admin", []),
    ("platform@example.test", "Local Platform Admin", ["platform_admin"]),
)
PATIENT_ADDRESS = {
    "address_line": "3 Temasek Boulevard, Singapore",
    "postal_code": "038983",
    "country_code": "SG",
}


def patient_phone():
    local = dotenv_values(Path("/state/accounts.env"))
    value = os.environ.get("LOCAL_SEED_PATIENT_PHONE") or local.get("LOCAL_SEED_PATIENT_PHONE", "")
    value = value.translate(str.maketrans("", "", " -()"))
    if len(value) == 8:
        value = "+65" + value
    if not re.fullmatch(r"\+65[689][0-9]{7}", value):
        raise ValueError(
            "Set LOCAL_SEED_PATIENT_PHONE to a Singapore phone "
            "in /state/accounts.env or the environment."
        )
    return value


def local_settings():
    settings = dotenv_values(Path("/state/identity.env"))
    database = urlsplit(
        settings.get("SERVICE_DATABASE_URL", "").replace("postgresql+psycopg:", "postgresql:")
    )
    if (
        settings.get("SERVICE_ENVIRONMENT") != "local"
        or settings.get("SERVICE_AWS_ENDPOINT_URL") != "http://floci:4566"
        or database.scheme != "postgresql"
        or database.hostname != "postgres"
        or database.port not in (None, 5432)
        or database.path != "/telelink"
        or database.username != "identity"
        or database.query
        or database.fragment
    ):
        raise ValueError("Expected the dedicated local Compose identity database and Floci.")
    return settings, database.geturl()


def context(settings):
    session = boto3.Session(
        aws_access_key_id="test", aws_secret_access_key="test", region_name="ap-southeast-1"
    )
    cognito = session.client("cognito-idp", endpoint_url="http://floci:4566")
    pools = [
        pool
        for page in cognito.get_paginator("list_user_pools").paginate(MaxResults=60)
        for pool in page["UserPools"]
        if pool["Name"] == "telelink-local"
    ]
    if len(pools) != 1:
        raise ValueError("Expected exactly one telelink-local user pool.")
    pool_id = pools[0]["Id"]
    issuer = urlsplit(settings.get("SERVICE_AUTH_ISSUER", ""))
    if (
        issuer.hostname not in {"localhost", "127.0.0.1", "floci"}
        or issuer.path.rstrip("/").split("/")[-1] != pool_id
    ):
        raise ValueError("Configured identity issuer does not match the local pool.")
    clients = [
        client
        for page in cognito.get_paginator("list_user_pool_clients").paginate(
            UserPoolId=pool_id, MaxResults=60
        )
        for client in page["UserPoolClients"]
        if client["ClientName"] == "telelink-web"
    ]
    if len(clients) != 1:
        raise ValueError("Expected exactly one telelink-web client.")
    return cognito, pool_id, clients[0]["ClientId"]


def provision(cognito, pool_id, database_url, password):
    with psycopg.connect(database_url) as database:
        for email, name, roles in ACCOUNTS:
            try:
                user = cognito.admin_get_user(UserPoolId=pool_id, Username=email)
            except cognito.exceptions.UserNotFoundException:
                cognito.admin_create_user(
                    UserPoolId=pool_id,
                    Username=email,
                    MessageAction="SUPPRESS",
                    TemporaryPassword=password,
                    UserAttributes=[
                        {"Name": "email", "Value": email},
                        {"Name": "email_verified", "Value": "true"},
                        {"Name": "name", "Value": name},
                    ],
                )
                user = cognito.admin_get_user(UserPoolId=pool_id, Username=email)
            attributes = {item["Name"]: item["Value"] for item in user["UserAttributes"]}
            if attributes.get("email", "").lower() != email:
                raise ValueError(f"Existing local Cognito email differs for {email}.")
            cognito.admin_set_user_password(
                UserPoolId=pool_id, Username=email, Password=password, Permanent=True
            )
            database.execute(
                "INSERT INTO identity.subjects "
                "(subject_id, cognito_sub, display_name, global_roles, email) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (cognito_sub) DO UPDATE SET "
                "display_name=EXCLUDED.display_name, global_roles=EXCLUDED.global_roles, "
                "email=EXCLUDED.email",
                (
                    uuid5(NAMESPACE_URL, "telelink:accounts-only:" + email),
                    attributes["sub"],
                    name,
                    roles,
                    email,
                ),
            )


def provision_profiles(database_url, phone):
    with psycopg.connect(database_url) as database:
        for email, _, roles in ACCOUNTS:
            if "patient" not in roles:
                continue
            database.execute(
                "INSERT INTO identity.patient_profiles "
                "(subject_id, phone_number, address_line, postal_code, country_code) "
                "SELECT subject_id, %s, %s, %s, %s FROM identity.subjects WHERE email=%s "
                "ON CONFLICT (subject_id) DO UPDATE SET "
                "phone_number=EXCLUDED.phone_number, address_line=EXCLUDED.address_line, "
                "postal_code=EXCLUDED.postal_code, country_code=EXCLUDED.country_code, "
                "updated_at=now()",
                (
                    phone,
                    PATIENT_ADDRESS["address_line"],
                    PATIENT_ADDRESS["postal_code"],
                    PATIENT_ADDRESS["country_code"],
                    email,
                ),
            )


def verify(cognito, client_id, database_url, password, phone):
    with (
        psycopg.connect(database_url) as database,
        httpx.Client(timeout=20, trust_env=False) as http,
    ):
        for email, _, roles in ACCOUNTS:
            rows = database.execute(
                "SELECT subject_id, global_roles FROM identity.subjects WHERE email=%s",
                (email,),
            ).fetchall()
            if len(rows) != 1 or rows[0][1] != roles:
                raise ValueError(f"Incorrect subject/global roles for {email}.")
            result = cognito.initiate_auth(
                ClientId=client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )
            response = http.get(
                "http://identity:8000/me",
                headers={
                    "Authorization": "Bearer " + result["AuthenticationResult"]["AccessToken"]
                },
            )
            response.raise_for_status()
            me = response.json()
            if str(rows[0][0]) != me["subject_id"] or me["global_roles"] != roles:
                raise ValueError(f"Identity API role verification failed for {email}.")
            if "patient" in roles:
                response = http.get(
                    "http://identity:8000/me/patient-profile",
                    headers={
                        "Authorization": "Bearer " + result["AuthenticationResult"]["AccessToken"]
                    },
                )
                response.raise_for_status()
                profile = response.json()
                expected = {**PATIENT_ADDRESS, "phone_number": phone}
                if any(profile.get(key) != value for key, value in expected.items()):
                    raise ValueError(f"Patient profile verification failed for {email}.")
            print(f"Verified login and global roles: {email}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Provision the five accounts.")
    parser.add_argument("--verify", action="store_true", help="Verify existing account logins.")
    args = parser.parse_args()
    settings, database_url = local_settings()
    cognito, pool_id, client_id = context(settings)
    with psycopg.connect(database_url) as database:
        if not database.execute("SELECT version_num FROM identity.alembic_version").fetchall():
            raise ValueError("Migrate identity before seeding accounts.")
        count = database.execute("SELECT count(*) FROM identity.subjects").fetchone()[0]
    print(f"Local preflight passed; {count} existing subjects.", flush=True)
    if not (args.apply or args.verify):
        print("No changes made. Use --apply with LOCAL_SEED_PASSWORD to provision accounts.")
        return
    password = os.environ.get("LOCAL_SEED_PASSWORD")
    if not password:
        raise ValueError("Set LOCAL_SEED_PASSWORD explicitly for local demo accounts.")
    phone = patient_phone()
    if args.apply:
        provision(cognito, pool_id, database_url, password)
        provision_profiles(database_url, phone)
    verify(cognito, client_id, database_url, password, phone)
    print("Five accounts ready. Doctor/admin clinic memberships are assigned separately.")


if __name__ == "__main__":
    main()
