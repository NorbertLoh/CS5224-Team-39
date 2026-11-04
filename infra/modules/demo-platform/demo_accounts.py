"""Add synthetic accounts to the domain-free demo after its migrations."""

import io
import json
import os
import secrets
from contextlib import closing
from uuid import NAMESPACE_URL, uuid5

import boto3
import psycopg
from reportlab.pdfgen import canvas

ROLES = ("patient", "doctor", "clinic_admin", "platform_admin")
DEMO_PASSWORD = "LocalDemo123!"


def demo_id(key):
    return uuid5(NAMESPACE_URL, f"telelink:aws-demo:{key}")


def read_secret(client, name):
    return json.loads(client.get_secret_value(SecretId=os.environ[name])["SecretString"])


def logins(client, pool):
    try:
        data = read_secret(client, "LOGIN_SECRET")
    except client.exceptions.ResourceNotFoundException:
        data = {
            "pool": pool,
            "accounts": {
                role: {
                    "email": f"{role.replace('_', '-')}-{secrets.token_hex(8)}@example.test",
                    "password": DEMO_PASSWORD,
                }
                for role in ROLES
            },
        }
        client.put_secret_value(
            SecretId=os.environ["LOGIN_SECRET"], SecretString=json.dumps(data)
        )
    if data["pool"] != pool:
        raise ValueError("Login secret belongs to a different Cognito pool")
    return data


def ensure_user(client, pool, role, login, password_changed):
    name = "Demo " + role.replace("_", " ").title()
    email = login["email"]
    if not email.endswith("@example.test"):
        raise ValueError("Demo login must use a reserved synthetic address")
    try:
        user = client.admin_get_user(UserPoolId=pool, Username=email)
    except client.exceptions.UserNotFoundException:
        user = client.admin_create_user(
            UserPoolId=pool,
            Username=email,
            TemporaryPassword=login["password"],
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "name", "Value": name},
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
        )["User"]
    attrs = {
        attr["Name"]: attr["Value"]
        for attr in user.get("UserAttributes", user.get("Attributes", []))
    }
    if (attrs.get("email"), attrs.get("name"), attrs.get("email_verified")) != (
        email,
        name,
        "true",
    ) or not user["Enabled"]:
        raise ValueError("Refusing to adopt a non-seeded or disabled user")
    if user["UserStatus"] not in ("CONFIRMED", "FORCE_CHANGE_PASSWORD"):
        raise ValueError("Unexpected demo account status")
    if password_changed or user["UserStatus"] == "FORCE_CHANGE_PASSWORD":
        client.admin_set_user_password(
            UserPoolId=pool, Username=email, Password=login["password"], Permanent=True
        )
    return attrs["sub"], name


def connect(config):
    url = config["database_url"].replace("postgresql+psycopg://", "postgresql://", 1)
    return psycopg.connect(url, sslmode="require", connect_timeout=10)


def seed():
    pool = os.environ["DEMO_POOL"]
    with (
        closing(boto3.client("secretsmanager")) as secrets_client,
        closing(boto3.client("cognito-idp")) as cognito,
        connect(read_secret(secrets_client, "IDENTITY_SECRET")) as identity,
    ):
        identity.execute("SELECT pg_advisory_xact_lock(57389041)")
        identity.execute("SELECT 1 FROM identity.doctor_applications LIMIT 1")
        with connect(read_secret(secrets_client, "TENANT_SECRET")) as tenant:
            tenant.execute("SELECT membership_provisioned FROM tenant.clinics LIMIT 1")
            login_data = logins(secrets_client, pool)
            accounts = login_data["accounts"]
            subjects = {}
            updated_password = False
            for role in ROLES:
                login = accounts[role]
                password_changed = login["password"] != DEMO_PASSWORD
                login["password"] = DEMO_PASSWORD
                sub, name = ensure_user(cognito, pool, role, login, password_changed)
                updated_password |= password_changed
                roles = [role] if role in ("patient", "platform_admin") else []
                subjects[role] = identity.execute(
                    """INSERT INTO identity.subjects
                       (subject_id, cognito_sub, display_name, global_roles, email)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (cognito_sub) DO NOTHING
                       RETURNING subject_id""",
                    (demo_id(sub), sub, name, roles, accounts[role]["email"]),
                ).fetchone() or identity.execute(
                    "SELECT subject_id FROM identity.subjects WHERE cognito_sub = %s", (sub,)
                ).fetchone()
            if updated_password:
                secrets_client.put_secret_value(
                    SecretId=os.environ["LOGIN_SECRET"], SecretString=json.dumps(login_data)
                )

            clinic = demo_id("clinic")
            tenant.execute(
                """INSERT INTO tenant.clinics
                   (tenant_id, slug, name, status, primary_color, description,
                    consultation_price_minor, creator_subject_id, membership_provisioned)
                   VALUES (%s, 'aws-demo-clinic', 'TeleLink Demo Clinic', 'active',
                    '#156B63', 'Synthetic demo clinic. No clinical services.', 3500, %s, true)
                   ON CONFLICT (tenant_id) DO NOTHING""",
                (clinic, subjects["clinic_admin"][0]),
            )
            for role in ("doctor", "clinic_admin"):
                identity.execute(
                    """INSERT INTO identity.memberships
                       (membership_id, subject_id, tenant_id, roles)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (subject_id, tenant_id) DO NOTHING""",
                    (demo_id(role), subjects[role][0], clinic, [role]),
                )
            doctor = subjects["doctor"][0]
            document = demo_id("doctor-document")
            pdf = io.BytesIO()
            page = canvas.Canvas(pdf)
            page.drawString(60, 760, "Synthetic demo credential. No clinical use.")
            page.save()
            identity.execute(
                """INSERT INTO identity.doctor_documents
                   (document_id, subject_id, content_type, content)
                   VALUES (%s, %s, 'application/pdf', %s)
                   ON CONFLICT (document_id) DO NOTHING""",
                (document, doctor, pdf.getvalue()),
            )
            identity.execute(
                """INSERT INTO identity.doctor_applications
                   (subject_id, legal_name, licence_number, licensing_authority,
                    specialty, document_id, status, revision, reviewed_at, reviewer_id)
                   VALUES (%s, 'Demo Doctor', 'DEMO-ONLY', 'Synthetic demo authority',
                           'General practice', %s, 'approved', 1, now(), %s)
                   ON CONFLICT (subject_id) DO NOTHING""",
                (doctor, document, subjects["platform_admin"][0]),
            )
    print("Verified four synthetic demo accounts and their application fixtures.")


if __name__ == "__main__":
    try:
        seed()
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"Demo account seed failed: {type(error).__name__}") from None
