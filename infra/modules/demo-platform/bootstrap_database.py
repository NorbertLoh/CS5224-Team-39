"""One-off ECS bootstrap: service roles/schemas only, no domain/demo records.

This command is deliberately separate from service startup and Alembic migrations.
All credentials are read from Secrets Manager at runtime.
"""

import json
import os
from contextlib import closing
from urllib.parse import unquote, urlsplit

import boto3
import psycopg
from psycopg import sql


def main():
    with closing(
        boto3.client("secretsmanager", region_name="ap-southeast-1")
    ) as client:
        master = json.loads(
            client.get_secret_value(SecretId=os.environ["DB_MASTER_SECRET_ARN"])[
                "SecretString"
            ]
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
        # Scheduling's UUID exclusion constraints require this GiST operator class.
        connection.execute(
            "CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public"
        )
        for owner, config in configs.items():
            url = urlsplit(config["database_url"])
            if (
                url.scheme != "postgresql+psycopg"
                or url.hostname != os.environ["DB_HOST"]
                or url.path != "/telelink"
                or unquote(url.username or "") != owner
                or not url.password
            ):
                raise ValueError(
                    "Service database configuration does not match its owner"
                )
            if not connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (owner,)
            ).fetchone():
                connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(owner))
                )
            connection.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(owner), sql.Literal(unquote(url.password))
                )
            )
            role = sql.Identifier(owner)
            # PostgreSQL 17 grants CREATEROLE users ADMIN without SET on new roles.
            # Keep the temporary SET grant and schema creation in one transaction.
            with connection.transaction():
                connection.execute(
                    sql.SQL(
                        "GRANT {} TO CURRENT_USER WITH SET TRUE, INHERIT FALSE "
                        "GRANTED BY CURRENT_USER"
                    ).format(role)
                )
                connection.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                        role, role
                    )
                )
                connection.execute(
                    sql.SQL(
                        "REVOKE {} FROM CURRENT_USER GRANTED BY CURRENT_USER"
                    ).format(role)
                )
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE telelink TO {}").format(
                    sql.Identifier(owner)
                )
            )
    print("Service roles and schemas configured; run each owning migration task next.")


if __name__ == "__main__":
    try:
        main()
    # Database/SDK errors can contain fetched credentials: expose the type only.
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"Database bootstrap failed: {type(error).__name__}") from None
