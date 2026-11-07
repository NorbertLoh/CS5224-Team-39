"""Explicit AWS-demo-only operation. Never invoked by Terraform apply or GET."""

import json
import os
import re
import socket
import ssl
import sys
import time
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

import boto3
import psycopg
from botocore.config import Config
from psycopg import sql
from psycopg.types.json import Jsonb
from requested_seed import ACCOUNTS, FIELDS, PATIENT_ADDRESS, application, licence_pdf

SCHEMAS = (
    "identity",
    "tenant",
    "scheduling",
    "consultation",
    "clinical_records",
    "billing",
    "fulfilment",
    "document",
    "notification",
)
KEY = "reset/state.json"


def seed_id(name):
    return uuid5(NAMESPACE_URL, "telelink:requested-demo:" + name)


def validate_config(config, seed):
    if config.get("deployment") != "demo" or not config["pool"].startswith("ap-southeast-1_"):
        raise ValueError("Only the explicit Singapore demo deployment is supported")
    phone = str(seed.get("patient_phone", "")).translate(str.maketrans("", "", " -()"))
    if len(phone) == 8:
        phone = "+65" + phone
    if not re.fullmatch(r"\+65[689][0-9]{7}", phone):
        raise ValueError("Configure the requested Singapore seed phone first")
    password = seed.get("new_account_password", "")
    if len(password) < 12:
        raise ValueError("Configure the password used only for missing seed accounts")
    return phone, password


def insert(connection, schema, table, **values):
    connection.execute(
        sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, values)),
            sql.SQL(",").join(sql.Placeholder() for _ in values),
        ),
        list(values.values()),
    )


def seed_database(connection, users, phone, evidence):
    """All application rows are replaced together, with no CASCADE outside the allowlist."""
    tables = connection.execute(
        "SELECT schemaname, tablename FROM pg_tables WHERE schemaname=ANY(%s) "
        "AND tablename <> 'alembic_version' ORDER BY schemaname, tablename",
        (list(SCHEMAS),),
    ).fetchall()
    if set(s for s, _ in tables) != set(SCHEMAS):
        raise ValueError("All nine migrated application schemas are required")
    connection.execute(
        sql.SQL("TRUNCATE {} RESTART IDENTITY").format(
            sql.SQL(",").join(
                sql.SQL("{}.{}").format(sql.Identifier(s), sql.Identifier(t)) for s, t in tables
            )
        )
    )
    ids = {}
    for email, name, roles in ACCOUNTS:
        user = users[email]
        ids[email] = user["subject_id"]
        insert(
            connection,
            "identity",
            "subjects",
            subject_id=user["subject_id"],
            cognito_sub=user["sub"],
            display_name=name,
            email=email,
            global_roles=roles,
        )
        if "patient" in roles:
            insert(
                connection,
                "identity",
                "patient_profiles",
                subject_id=user["subject_id"],
                phone_number=phone,
                **PATIENT_ADDRESS,
            )
    clinic = application(phone)
    tenant_id = seed_id("meridian")
    admin = ids["clinic@example.test"]
    doctor = ids["doctor@example.test"]
    insert(
        connection,
        "tenant",
        "clinics",
        tenant_id=tenant_id,
        slug=clinic["slug"],
        name=clinic["name"],
        status="pending_review",
        creator_subject_id=admin,
        membership_provisioned=True,
        primary_color=clinic["branding"]["primary_color"],
        description=clinic["branding"]["description"],
        consultation_price_minor=3000,
        currency="SGD",
        commission_bps=0,
    )
    insert(
        connection,
        "tenant",
        "clinic_locations",
        tenant_id=tenant_id,
        location=Jsonb(clinic["location"]),
        updated_by=admin,
    )
    for subject, role in ((admin, "clinic_admin"), (doctor, "doctor")):
        insert(
            connection,
            "identity",
            "memberships",
            membership_id=seed_id(role),
            subject_id=subject,
            tenant_id=tenant_id,
            roles=[role],
            status="active",
        )
    document_id = seed_id("doctor-licence")
    insert(
        connection,
        "identity",
        "doctor_documents",
        document_id=document_id,
        subject_id=doctor,
        content_type="application/pdf",
        content=evidence,
        filename="Dr. Tan - Licence.pdf",
    )
    insert(
        connection,
        "identity",
        "doctor_applications",
        subject_id=doctor,
        document_id=document_id,
        status="pending",
        revision=1,
        **FIELDS,
    )
    snapshot = connection.execute(
        "SELECT to_jsonb(a) FROM identity.doctor_applications a WHERE subject_id=%s",
        (doctor,),
    ).fetchone()[0]
    insert(
        connection,
        "identity",
        "doctor_application_events",
        event_id=seed_id("submitted"),
        subject_id=doctor,
        actor_id=doctor,
        action="submitted",
        snapshot=Jsonb(snapshot),
    )
    counts = connection.execute(
        "SELECT (SELECT count(*) FROM identity.subjects), "
        "(SELECT count(*) FROM tenant.clinics WHERE status='pending_review'), "
        "(SELECT count(*) FROM identity.doctor_applications WHERE status='pending'), "
        "(SELECT count(*) FROM identity.memberships WHERE status='active')"
    ).fetchone()
    if counts != (5, 1, 1, 2):
        raise ValueError("Seed verification failed")
    stored = connection.execute(
        "SELECT content FROM identity.doctor_documents WHERE document_id=%s",
        (document_id,),
    ).fetchone()[0]
    if bytes(stored) != evidence:
        raise ValueError("Evidence verification failed")


class ResetJob:
    def __init__(self, config, request_id, clients):
        self.config, self.request_id, self.clients = config, request_id, clients

    def read(self):
        result = self.clients["s3"].get_object(Bucket=self.config["bucket"], Key=KEY)
        with closing(result["Body"]) as body:
            state = json.loads(body.read())
        if state["request_id"] != self.request_id:
            raise ValueError("This worker no longer owns the reset claim")
        return state, result["ETag"]

    def update(self, status, stage, **changes):
        state, etag = self.read()
        state.update(
            status=status, stage=stage, updated_at=datetime.now(timezone.utc).isoformat(), **changes
        )
        self.clients["s3"].put_object(
            Bucket=self.config["bucket"],
            Key=KEY,
            Body=json.dumps(state).encode(),
            ContentType="application/json",
            IfMatch=etag,
        )

    def secret(self, arn):
        return json.loads(
            self.clients["secretsmanager"].get_secret_value(SecretId=arn)["SecretString"]
        )

    def users(self, connection, password):
        users = {}
        client = self.clients["cognito-idp"]
        pool = self.config["pool"]
        for email, name, _ in ACCOUNTS:
            created = False
            try:
                user = client.admin_get_user(UserPoolId=pool, Username=email)
            except client.exceptions.UserNotFoundException:
                client.admin_create_user(
                    UserPoolId=pool,
                    Username=email,
                    MessageAction="SUPPRESS",
                    TemporaryPassword=password,
                    UserAttributes=[
                        {"Name": "email", "Value": email},
                        {"Name": "email_verified", "Value": "true"},
                        {"Name": "name", "Value": name},
                    ],
                )
                user = client.admin_get_user(UserPoolId=pool, Username=email)
                created = True
            attrs = {a["Name"]: a["Value"] for a in user["UserAttributes"]}
            if (
                attrs.get("email") != email
                or attrs.get("email_verified") != "true"
                or not user["Enabled"]
            ):
                raise ValueError("A seed account is disabled or has unexpected attributes")
            if user["UserStatus"] not in {"CONFIRMED", "FORCE_CHANGE_PASSWORD"}:
                raise ValueError("A seed account has an unsupported authentication state")
            if created or user["UserStatus"] == "FORCE_CHANGE_PASSWORD":
                client.admin_set_user_password(
                    UserPoolId=pool,
                    Username=user["Username"],
                    Password=password,
                    Permanent=True,
                )
            row = connection.execute(
                "SELECT subject_id FROM identity.subjects WHERE cognito_sub=%s",
                (attrs["sub"],),
            ).fetchone()
            users[email] = {"sub": attrs["sub"], "subject_id": row[0] if row else seed_id(email)}
        state, _ = self.read()
        if str(users["platform@example.test"]["subject_id"]) != state["actor_id"]:
            raise ValueError("The reset would remove its requesting administrator")
        return users

    def clear_queues(self):
        self.update("running", "Clearing old demo messages")
        sqs = self.clients["sqs"]
        for url in self.config["queues"]:
            # A purge-in-progress is a failure: never claim a completed reset prematurely.
            sqs.purge_queue(QueueUrl=url)
        time.sleep(65)  # SQS purge may take up to 60 seconds.
        for url in self.config["queues"]:
            attrs = sqs.get_queue_attributes(
                QueueUrl=url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                ],
            )["Attributes"]
            if any(int(n) for n in attrs.values()):
                raise ValueError("A demo queue did not settle after purge")

    def clear_redis(self):
        # The dedicated managed demo cache uses TLS, no password and only database 0.
        with socket.create_connection((self.config["redis_host"], 6379), timeout=10) as raw:
            with ssl.create_default_context().wrap_socket(
                raw, server_hostname=self.config["redis_host"]
            ) as stream:
                stream.sendall(b"*1\r\n$7\r\nFLUSHDB\r\n")
                with stream.makefile("rb") as response:
                    reply = response.readline(128)
                if reply != b"+OK\r\n":
                    raise ValueError("The dedicated demo cache was not cleared")

    def run(self):
        phone, password = validate_config(self.config, self.secret(self.config["seed_secret"]))
        if self.clients["sts"].get_caller_identity()["Account"] != self.config["account"]:
            raise ValueError("Wrong AWS account")
        evidence = licence_pdf()  # Render before taking any application offline.
        master = self.secret(self.config["master_secret"])
        with psycopg.connect(
            host=self.config["db_host"],
            dbname="telelink",
            user=master["username"],
            password=master["password"],
            sslmode="require",
            connect_timeout=10,
            autocommit=True,
        ) as connection:
            if not connection.execute("SELECT pg_try_advisory_lock(57389057)").fetchone()[0]:
                return  # A duplicate worker may not release or fail the active worker's claim.
            state, _ = self.read()
            if state["status"] != "queued":
                return
            self.update("running", "Checking demo seed accounts")
            granted = []
            quiesced = False
            try:
                for owner in SCHEMAS:
                    row = connection.execute(
                        "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (owner,)
                    ).fetchone()
                    if row != (True,):
                        raise ValueError("Expected a ready service database role")
                    previous = connection.execute(
                        "SELECT admin_option, inherit_option, set_option FROM pg_auth_members "
                        "WHERE roleid=(SELECT oid FROM pg_roles WHERE rolname=%s) "
                        "AND member=(SELECT oid FROM pg_roles WHERE rolname=current_user) "
                        "AND grantor=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                        (owner,),
                    ).fetchone()
                    # Bootstrap created these roles; temporary inheritance is revoked below.
                    connection.execute(
                        sql.SQL(
                            "GRANT {} TO CURRENT_USER WITH INHERIT TRUE, "
                            "SET FALSE GRANTED BY CURRENT_USER"
                        ).format(sql.Identifier(owner))
                    )
                    granted.append((owner, previous))
                    connection.execute(
                        sql.SQL("SELECT version_num FROM {}.alembic_version").format(
                            sql.Identifier(owner)
                        )
                    ).fetchone()
                users = self.users(connection, password)
                self.update("running", "Pausing demo database access", roles_quiesced=True)
                with connection.transaction():
                    for owner in SCHEMAS:
                        connection.execute(
                            sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(owner))
                        )
                quiesced = True
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=current_database() AND usename=ANY(%s) "
                    "AND pid<>pg_backend_pid()",
                    (list(SCHEMAS),),
                )
                # Existing API/Lambda invocations must finish before clearing async state.
                self.update("running", "Waiting for active demo requests to finish")
                time.sleep(150)
                self.clear_queues()
                self.update("running", "Restoring five accounts and two pending applications")
                with connection.transaction():
                    connection.execute("SET LOCAL lock_timeout = '10s'")
                    seed_database(connection, users, phone, evidence)
                self.clear_redis()
            finally:
                # Even a failed seed transaction is rolled back before reconnecting services.
                if quiesced:
                    with connection.transaction():
                        for owner in SCHEMAS:
                            connection.execute(
                                sql.SQL("ALTER ROLE {} LOGIN").format(sql.Identifier(owner))
                            )
                for owner, previous in reversed(granted):
                    if previous is None:
                        connection.execute(
                            sql.SQL("REVOKE {} FROM CURRENT_USER GRANTED BY CURRENT_USER").format(
                                sql.Identifier(owner)
                            )
                        )
                    else:
                        connection.execute(
                            sql.SQL(
                                "GRANT {} TO CURRENT_USER WITH ADMIN {}, INHERIT {}, SET {} "
                                "GRANTED BY CURRENT_USER"
                            ).format(
                                sql.Identifier(owner),
                                *(sql.SQL("TRUE" if flag else "FALSE") for flag in previous),
                            )
                        )
                if quiesced:
                    self.update("running", "Reconnecting demo services", roles_quiesced=False)
            self.update("succeeded", "Demo seed restored", roles_quiesced=False)


def main():
    config = json.loads(os.environ["RESET_CONFIG"])
    request_id = str(UUID(os.environ["RESET_REQUEST_ID"]))
    with ExitStack() as stack:
        clients = {
            name: stack.enter_context(
                closing(
                    boto3.client(
                        name,
                        region_name="ap-southeast-1",
                        config=Config(
                            connect_timeout=5,
                            read_timeout=15,
                            retries={"mode": "standard", "max_attempts": 3},
                        ),
                    )
                )
            )
            for name in ("s3", "secretsmanager", "cognito-idp", "sqs", "sts")
        }
        job = ResetJob(config, request_id, clients)
        try:
            job.run()
        except Exception as error:
            # Provider/DB exceptions can expose credentials. Persist only the error type.
            try:
                state, _ = job.read()
                if state["status"] in {"queued", "running"}:
                    job.update(
                        "failed",
                        "Reset failed; check operator recovery instructions",
                        error_type=type(error).__name__,
                    )
            except Exception as status_error:
                print(
                    f"Could not persist reset status: {type(status_error).__name__}",
                    file=sys.stderr,
                )
            print(f"Demo reset failed: {type(error).__name__}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
