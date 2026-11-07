"""Explicit AWS-demo-only operation. Never invoked by Terraform apply or GET."""

import json
import os
import re
import socket
import ssl
import sys
import time
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timezone
from uuid import UUID

import boto3
import psycopg
from botocore.config import Config
from psycopg import sql
from requested_database import SCHEMAS, seed_database, seed_users
from requested_seed import licence_pdf

KEY = "reset/state.json"


def validate_config(config, seed):
    if config.get("deployment") != "demo" or not config["pool"].startswith(
        "ap-southeast-1_"
    ):
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
            status=status,
            stage=stage,
            updated_at=datetime.now(timezone.utc).isoformat(),
            **changes,
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
            self.clients["secretsmanager"].get_secret_value(SecretId=arn)[
                "SecretString"
            ]
        )

    def users(self, connection, password):
        state, _ = self.read()
        return seed_users(
            connection,
            self.clients["cognito-idp"],
            self.config["pool"],
            password,
            state["actor_id"],
        )

    def set_dispatch_state(self, state):
        client = self.clients["scheduler"]
        schedule = client.get_schedule(
            Name=self.config["dispatch_schedule"], GroupName="default"
        )
        if schedule["Target"]["RoleArn"] != self.config["dispatch_schedule_role"]:
            raise ValueError("Unexpected notification schedule target role")
        if state is not None:
            # UpdateSchedule replaces omitted fields: preserve all supported settings.
            fields = client.meta.service_model.operation_model(
                "UpdateSchedule"
            ).input_shape.members
            values = {key: value for key, value in schedule.items() if key in fields}
            values.update(
                Name=self.config["dispatch_schedule"], GroupName="default", State=state
            )
            client.update_schedule(**values)
        return schedule["State"]

    @contextmanager
    def paused_dispatch(self):
        if not self.config.get("dispatch_schedule"):
            yield
            return
        previous = self.set_dispatch_state(None)
        if previous not in {"ENABLED", "DISABLED"}:
            raise ValueError("Unexpected notification schedule state")
        self.update(
            "running",
            "Pausing scheduled notifications",
            dispatch_original_state=previous,
            dispatch_paused=previous == "ENABLED",
        )
        try:
            if previous == "ENABLED":
                self.set_dispatch_state("DISABLED")
            yield
        finally:
            if previous == "ENABLED":
                self.set_dispatch_state(previous)
            self.update(
                "running", "Scheduled notifications restored", dispatch_paused=False
            )

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
        with socket.create_connection(
            (self.config["redis_host"], 6379), timeout=10
        ) as raw:
            with ssl.create_default_context().wrap_socket(
                raw, server_hostname=self.config["redis_host"]
            ) as stream:
                stream.sendall(b"*1\r\n$7\r\nFLUSHDB\r\n")
                with stream.makefile("rb") as response:
                    reply = response.readline(128)
                if reply != b"+OK\r\n":
                    raise ValueError("The dedicated demo cache was not cleared")

    def run(self):
        phone, password = validate_config(
            self.config, self.secret(self.config["seed_secret"])
        )
        if (
            self.clients["sts"].get_caller_identity()["Account"]
            != self.config["account"]
        ):
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
            if not connection.execute(
                "SELECT pg_try_advisory_lock(57389057)"
            ).fetchone()[0]:
                return  # A duplicate worker may not release or fail the active worker's claim.
            state, _ = self.read()
            if state["status"] != "queued":
                return
            self.update("running", "Checking demo seed accounts")
            with self.paused_dispatch():
                granted = []
                quiesced = False
                try:
                    for owner in SCHEMAS:
                        row = connection.execute(
                            "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s",
                            (owner,),
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
                            sql.SQL(
                                "SELECT version_num FROM {}.alembic_version"
                            ).format(sql.Identifier(owner))
                        ).fetchone()
                    users = self.users(connection, password)
                    self.update(
                        "running", "Pausing demo database access", roles_quiesced=True
                    )
                    with connection.transaction():
                        for owner in SCHEMAS:
                            connection.execute(
                                sql.SQL("ALTER ROLE {} NOLOGIN").format(
                                    sql.Identifier(owner)
                                )
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
                    self.update(
                        "running",
                        "Restoring five accounts and two pending applications",
                    )
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
                                    sql.SQL("ALTER ROLE {} LOGIN").format(
                                        sql.Identifier(owner)
                                    )
                                )
                    for owner, previous in reversed(granted):
                        if previous is None:
                            connection.execute(
                                sql.SQL(
                                    "REVOKE {} FROM CURRENT_USER GRANTED BY CURRENT_USER"
                                ).format(sql.Identifier(owner))
                            )
                        else:
                            connection.execute(
                                sql.SQL(
                                    "GRANT {} TO CURRENT_USER WITH ADMIN {}, INHERIT {}, SET {} "
                                    "GRANTED BY CURRENT_USER"
                                ).format(
                                    sql.Identifier(owner),
                                    *(
                                        sql.SQL("TRUE" if flag else "FALSE")
                                        for flag in previous
                                    ),
                                )
                            )
                    if quiesced:
                        self.update(
                            "running",
                            "Reconnecting demo services",
                            roles_quiesced=False,
                        )
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
            for name in (
                "s3",
                "secretsmanager",
                "cognito-idp",
                "sqs",
                "sts",
                "scheduler",
            )
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
