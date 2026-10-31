"""One-off ECS bootstrap: service roles/schemas only, no domain/demo records.

This command is deliberately separate from service startup and Alembic migrations.
All credentials are read from Secrets Manager at runtime.
"""

import json
import os
from urllib.parse import unquote, urlsplit

import boto3
import psycopg
from psycopg import sql


def main():
    with boto3.client("secretsmanager", region_name="ap-southeast-1") as client:
        master = json.loads(
            client.get_secret_value(SecretId=os.environ["DB_MASTER_SECRET_ARN"])["SecretString"]
        )
        configs = {
            owner: json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
            for owner, arn in json.loads(os.environ["SERVICE_CONFIG_ARNS"]).items()
        }
    with psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname="telelink",
        user=master["username"],
        password=master["password"],
        sslmode="require",
        connect_timeout=10,
        autocommit=True,
    ) as connection:
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        for owner, config in configs.items():
            url = urlsplit(config["database_url"])
            if (
                url.scheme != "postgresql+psycopg"
                or url.hostname != os.environ["DB_HOST"]
                or url.path != "/telelink"
                or unquote(url.username or "") != owner
                or not url.password
            ):
                raise ValueError("Service database configuration does not match its owner")
            if not connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (owner,)
            ).fetchone():
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(owner)))
            connection.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(owner), sql.Literal(unquote(url.password))
                )
            )
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                    sql.Identifier(owner), sql.Identifier(owner)
                )
            )
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE telelink TO {}").format(sql.Identifier(owner))
            )
    print("Service roles and schemas configured; run each owning migration task next.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Database bootstrap failed: {type(error).__name__}") from None
