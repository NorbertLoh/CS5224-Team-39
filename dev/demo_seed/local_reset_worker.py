"""Opt-in Compose worker for explicit local reset requests; never connects to AWS."""

import os
import socket
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import boto3
import psycopg
from accounts import context, local_settings, patient_phone
from psycopg import sql
from requested_database import SCHEMAS, seed_database, seed_users
from requested_seed import licence_pdf
from telelink_common.file_jobs import FileJobs

STATE = Path("/reset-state")
AWS = {
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
    "region_name": "ap-southeast-1",
    "endpoint_url": "http://floci:4566",
}


def preflight():
    configs = {owner: local_settings(owner)[0] for owner in SCHEMAS}
    phone = patient_phone()
    password = os.environ.get("LOCAL_SEED_PASSWORD", "")
    if len(password) < 12 or not os.environ.get("POSTGRES_PASSWORD"):
        raise ValueError("Configure the local administrator and new-account passwords")
    cognito, pool, _ = context(configs["identity"])
    return configs, phone, password, cognito, pool


def admin():
    return psycopg.connect(
        host="postgres",
        port=5432,
        dbname="telelink",
        user="postgres",
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=5,
        autocommit=True,
    )


def clear_queues(sqs):
    queues = [
        url
        for page in sqs.get_paginator("list_queues").paginate(QueueNamePrefix="telelink-local-")
        for url in page.get("QueueUrls", [])
    ]
    normalized = []
    for value in queues:
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"floci", "localhost"}
            or url.port != 4566
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not url.path.rsplit("/", 1)[-1].startswith("telelink-local-")
        ):
            raise ValueError("Only local Floci queues may be purged")
        normalized.append("http://floci:4566" + url.path)
    queues = normalized
    for url in queues:
        sqs.purge_queue(QueueUrl=url)
    time.sleep(65)
    for url in queues:
        values = sqs.get_queue_attributes(
            QueueUrl=url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
            ],
        )["Attributes"]
        if any(int(value) for value in values.values()):
            raise ValueError("Local queues have not emptied")


def clear_cache():
    # A fixed dedicated Compose cache; browser requests cannot choose a target.
    with socket.create_connection(("redis", 6379), timeout=5) as stream:
        stream.sendall(b"*1\r\n$7\r\nFLUSHDB\r\n")
        with stream.makefile("rb") as response:
            if response.readline(128) != b"+OK\r\n":
                raise ValueError("The local cache was not cleared")


def run(jobs, state):
    UUID(state["request_id"])
    _, phone, password, cognito, pool = preflight()
    evidence = licence_pdf()
    with closing(cognito), closing(boto3.client("sqs", **AWS)) as sqs, admin() as connection:
        if not connection.execute("SELECT pg_try_advisory_lock(57389057)").fetchone()[0]:
            raise RuntimeError("Another reset holds the database lock")
        for owner in SCHEMAS:
            connection.execute(
                sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(owner))
            ).fetchone()
            if connection.execute(
                "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (owner,)
            ).fetchone() != (True,):
                raise ValueError("Restore the local service role before resetting")
        # Read and preserve existing login IDs before touching application rows.
        users = seed_users(connection, cognito, pool, password, state["actor_id"])
        quiesced = False
        try:
            state["roles_quiesced"] = True
            jobs.update(state, "running", "Pausing local database access")
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
            jobs.update(state, "running", "Waiting for active local requests to finish")
            time.sleep(150)
            jobs.update(state, "running", "Clearing old local messages")
            clear_queues(sqs)
            jobs.update(state, "running", "Restoring five accounts and two pending applications")
            with connection.transaction():
                connection.execute("SET LOCAL lock_timeout = '10s'")
                seed_database(connection, users, phone, evidence)
            clear_cache()
        finally:
            if quiesced:
                with connection.transaction():
                    for owner in SCHEMAS:
                        connection.execute(
                            sql.SQL("ALTER ROLE {} LOGIN").format(sql.Identifier(owner))
                        )
                state["roles_quiesced"] = False
                jobs.update(state, "running", "Reconnecting local services")
    jobs.update(state, "succeeded", "Local seed restored")


def main():
    # A startup preflight validates fixed local targets without creating a job.
    with closing(preflight()[3]):
        pass
    jobs = FileJobs(STATE)
    while True:
        jobs.heartbeat()
        state = jobs.read()
        if state and state.get("status") == "queued":
            try:
                with jobs.claim():
                    state = jobs.read()
                    if state and state["status"] == "queued":
                        try:
                            jobs.update(state, "running", "Checking local reset configuration")
                            run(jobs, state)
                        except Exception as error:
                            state["error_type"] = type(error).__name__
                            jobs.update(
                                state, "failed", "Local reset failed; check recovery instructions"
                            )
                            print(f"Local reset failed: {type(error).__name__}", flush=True)
            except FileExistsError:
                pass  # Another API/worker holds the claim. Never bypass it automatically.
        time.sleep(1)


if __name__ == "__main__":
    main()
