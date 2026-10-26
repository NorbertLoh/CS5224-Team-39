"""Local host-stack configuration and the reset boundary (never AWS)."""

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import dotenv_values

SCHEMAS = [
    "identity",
    "tenant",
    "scheduling",
    "consultation",
    "clinical_records",
    "billing",
    "fulfilment",
    "document",
    "notification",
]
CONTAINERS = {
    "postgres": "telelink-clinic-postgres",
    "floci": "telelink-floci-1",
    "redis": "telelink-redis-1",
    "stripe": "telelink-local-stripe-forwarder",
}


def local_url(value, schemes, *, root_path=False):
    url = urlsplit(value)
    if (
        url.scheme not in schemes
        or url.hostname not in {"localhost", "127.0.0.1"}
        or url.query
        or url.fragment
        or (root_path and url.path not in {"", "/"})
    ):
        raise ValueError("Seed targets must be explicit loopback URLs.")
    return url


def app_origin(value):
    url = urlsplit(value)
    local = url.hostname in {"localhost", "127.0.0.1"}
    tailnet = (url.hostname or "").endswith(".ts.net")
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or not (local or tailnet)
        or url.scheme not in ({"http", "https"} if local else {"https"})
    ):
        raise ValueError("App origin must be localhost HTTP/HTTPS or tailnet HTTPS.")
    return value.rstrip("/")


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def inspect_container(name):
    return json.loads(docker("inspect", name))[0]


def published_port(container, internal_port, host_port):
    bindings = container["NetworkSettings"]["Ports"].get(f"{internal_port}/tcp") or []
    if not any(b["HostIp"] == "127.0.0.1" and int(b["HostPort"]) == host_port for b in bindings):
        raise ValueError("Configured endpoint does not match the local Docker container port.")
    if not container["State"]["Running"]:
        raise ValueError("Start the supported local host-stack dependencies first.")


class Environment:
    def __init__(self, root, origin):
        self.root = Path(root).resolve()
        self.state = self.root / ".local/demo-seed"
        self.origin = app_origin(origin)
        self.source = Path(__file__).resolve().parent
        self.config = {}
        self.backup = None
        self.checked = False
        self.stripe_was_running = False

    def local_file(self, value):
        path = Path(value)
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_relative_to((self.root / ".local").resolve()):
            raise ValueError(
                "Delivery configuration must be inside this checkout's .local directory."
            )
        if not path.is_file():
            raise ValueError("Configured delivery file does not exist.")
        return path

    def preflight(self):
        if any(
            os.environ.get(key)
            for key in (
                "SERVICE_DATABASE_URL",
                "SERVICE_ENVIRONMENT",
                "SERVICE_AWS_ENDPOINT_URL",
                "SERVICE_REDIS_URL",
            )
        ):
            raise ValueError("Unset SERVICE_* target overrides before using the demo seed.")
        if not (self.root / "dev/local_stack.ps1").is_file():
            raise ValueError("Root must be a TeleLink checkout with the host launcher.")
        addresses = set()
        for service in SCHEMAS:
            cfg = dotenv_values(self.root / f"services/{service}/.env")
            if cfg.get("SERVICE_ENVIRONMENT") != "local":
                raise ValueError(f"{service}: SERVICE_ENVIRONMENT must explicitly be local.")
            url = local_url(
                cfg.get("SERVICE_DATABASE_URL", "").replace(
                    "postgresql+psycopg://", "postgresql://"
                ),
                {"postgresql"},
            )
            if url.path != "/telelink" or url.username != service or not url.port:
                raise ValueError(f"{service}: expected the service-owned local telelink database.")
            addresses.add((url.hostname, url.port, url.path))
            if cfg.get("SERVICE_AWS_ENDPOINT_URL"):
                local_url(cfg["SERVICE_AWS_ENDPOINT_URL"], {"http"}, root_path=True)
            self.config[service] = cfg
        if len(addresses) != 1:
            raise ValueError("All services must target the same local database.")
        self.database = urlsplit(
            self.config["identity"]["SERVICE_DATABASE_URL"].replace(
                "postgresql+psycopg://", "postgresql://"
            )
        )
        pg = inspect_container(CONTAINERS["postgres"])
        if not pg["Config"]["Image"].startswith("postgres:"):
            raise ValueError("Expected the host guide's PostgreSQL container.")
        published_port(pg, 5432, self.database.port)
        pg_env = dict(v.split("=", 1) for v in pg["Config"]["Env"] if "=" in v)
        self.pg_user = pg_env.get("POSTGRES_USER", "postgres")
        self.pg_password = pg_env["POSTGRES_PASSWORD"]
        self.aws_endpoint = self.config["document"].get("SERVICE_AWS_ENDPOINT_URL", "")
        aws_url = local_url(self.aws_endpoint, {"http"}, root_path=True)
        if aws_url.username or aws_url.password or not aws_url.port:
            raise ValueError(
                "The local emulator URL must have an explicit port and no credentials."
            )
        for cfg in self.config.values():
            if cfg.get("SERVICE_AWS_ENDPOINT_URL") and cfg["SERVICE_AWS_ENDPOINT_URL"].rstrip(
                "/"
            ) != self.aws_endpoint.rstrip("/"):
                raise ValueError("All AWS SDK endpoints must target the same local emulator.")
        floci = inspect_container(CONTAINERS["floci"])
        if not floci["Config"]["Image"].startswith("floci/floci:"):
            raise ValueError("Only the project's Floci emulator is supported.")
        published_port(floci, 4566, aws_url.port)
        if not any(m["Destination"] == "/app/data" for m in floci["Mounts"]):
            raise ValueError("Persistent emulator storage is required for backup.")
        redis = local_url(self.config["scheduling"].get("SERVICE_REDIS_URL", ""), {"redis"})
        if redis.path not in {"", "/", "/0"} or redis.username or redis.password:
            raise ValueError("Only the dedicated local Redis database 0 is supported.")
        published_port(inspect_container(CONTAINERS["redis"]), 6379, redis.port or 6379)
        self.aws_options = dict(
            endpoint_url=self.aws_endpoint,
            region_name=self.config["document"].get("SERVICE_AWS_REGION", "ap-southeast-1"),
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        self.buckets = [
            self.config["document"].get("SERVICE_DOCUMENT_BUCKET", "telelink-local-documents"),
            self.config["tenant"].get("SERVICE_LOGO_BUCKET", "telelink-local-branding"),
        ]
        if any(not bucket.startswith("telelink-local-") for bucket in self.buckets):
            raise ValueError("Only telelink-local-* document/branding buckets may be reset.")
        cognito = boto3.client("cognito-idp", **self.aws_options)
        pools = [
            p
            for p in cognito.list_user_pools(MaxResults=60)["UserPools"]
            if p["Name"] == "telelink-local"
        ]
        if len(pools) != 1:
            raise ValueError("Run the local Cognito bootstrap first.")
        self.pool = pools[0]["Id"]
        web = dotenv_values(self.root / "apps/web/.env")
        self.client_id = web.get("VITE_COGNITO_CLIENT_ID")
        if web.get("VITE_USE_AWS", "").lower() != "false" or not self.client_id:
            raise ValueError("Frontend must explicitly use local Cognito.")
        client = cognito.describe_user_pool_client(UserPoolId=self.pool, ClientId=self.client_id)[
            "UserPoolClient"
        ]
        if "ALLOW_USER_PASSWORD_AUTH" not in client.get("ExplicitAuthFlows", []):
            raise ValueError("The existing local SPA client must support demo password sign-in.")
        self.document_python = self.root / "services/document/.venv/Scripts/python.exe"
        if not self.document_python.is_file():
            raise ValueError("Set up the document service virtualenv first (Windows host stack).")
        for key in [
            "SERVICE_DELIVERY_CONTACTS_PATH",
            "SERVICE_DELIVERY_LOCATIONS_PATH",
        ]:
            if self.config["fulfilment"].get(key):
                path = self.local_file(self.config["fulfilment"][key])
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                sections = (
                    ["senders", "recipients"]
                    if key.endswith("CONTACTS_PATH")
                    else ["origins", "destinations"]
                )
                if any(not isinstance(value.get(s), dict) or not value[s] for s in sections):
                    raise ValueError(
                        "Existing sandbox contact/location directories must have usable examples."
                    )
        # Confirm schemas exist and reject Compose API replicas before stopping anything.
        with self.admin() as connection:
            schemas = {
                r[0]
                for r in connection.execute("SELECT schema_name FROM information_schema.schemata")
            }
            if not set(SCHEMAS).issubset(schemas):
                raise ValueError("Migrate all nine local services before seeding.")
        if docker(
            "ps",
            "--filter",
            "label=com.docker.compose.service=identity",
            "--format",
            "{{.ID}}",
        ):
            raise ValueError("This command supports the host launcher, not running Compose APIs.")
        self.checked = True

    def admin(self):
        return psycopg.connect(
            host=self.database.hostname,
            port=self.database.port,
            dbname="telelink",
            user=self.pg_user,
            password=self.pg_password,
        )

    def launcher(self, action):
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.root / "dev/local_stack.ps1"),
                action,
            ],
            check=True,
        )

    def flush_redis(self):
        self.require_backup()
        docker("exec", CONTAINERS["redis"], "redis-cli", "-n", "0", "FLUSHDB")

    def stop(self):
        if not self.checked:
            raise RuntimeError("Preflight must pass before stopping the stack.")
        self.launcher("stop")
        if docker("ps", "--filter", f"name=^/{CONTAINERS['stripe']}$", "--format", "{{.ID}}"):
            self.stripe_was_running = True
            docker("stop", CONTAINERS["stripe"])

    def start(self):
        if self.stripe_was_running:
            docker("start", CONTAINERS["stripe"])
        self.launcher("start")

    def take_backup(self):
        if not self.checked:
            raise RuntimeError("Preflight must pass before backup.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.state / "backups" / stamp
        backup.mkdir(parents=True)
        dump = "/tmp/telelink-demo-seed.dump"
        docker(
            "exec",
            CONTAINERS["postgres"],
            "pg_dump",
            "-U",
            self.pg_user,
            "-d",
            "telelink",
            "-Fc",
            "-f",
            dump,
        )
        contents = docker("exec", CONTAINERS["postgres"], "pg_restore", "--list", dump)
        (backup / "database-contents.txt").write_text(contents, encoding="utf-8")
        docker("cp", f"{CONTAINERS['postgres']}:{dump}", str(backup / "database.dump"))
        docker("exec", CONTAINERS["redis"], "redis-cli", "SAVE")
        docker("cp", f"{CONTAINERS['redis']}:/data", str(backup / "redis-data"))
        docker("stop", CONTAINERS["floci"])
        try:
            docker("cp", f"{CONTAINERS['floci']}:/app/data", str(backup / "floci-data"))
        finally:
            docker("start", CONTAINERS["floci"])
        config = backup / "config"
        config.mkdir()
        for service in SCHEMAS:
            shutil.copy2(self.root / f"services/{service}/.env", config / f"{service}.env")
        shutil.copy2(self.root / "apps/web/.env", config / "web.env")
        if (self.root / ".env").is_file():
            shutil.copy2(self.root / ".env", config / "root.env")
        for key in [
            "SERVICE_DELIVERY_CONTACTS_PATH",
            "SERVICE_DELIVERY_LOCATIONS_PATH",
        ]:
            if self.config["fulfilment"].get(key):
                shutil.copy2(
                    self.local_file(self.config["fulfilment"][key]),
                    config / f"{key}.json",
                )
        data = (backup / "database.dump").read_bytes()
        if len(data) < 1000 or not (backup / "floci-data").is_dir():
            raise RuntimeError("Backup validation failed; reset was not started.")
        (backup / "complete.json").write_text(
            json.dumps(
                {"sha256": hashlib.sha256(data).hexdigest(), "root": str(self.root)},
                indent=2,
            ),
            encoding="utf-8",
        )
        self.backup = backup
        health_client = boto3.client(
            "cognito-idp",
            **self.aws_options,
            config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 0}),
        )
        for _ in range(60):
            restarted = inspect_container(CONTAINERS["floci"])
            published_port(restarted, 4566, urlsplit(self.aws_endpoint).port)
            if restarted["State"]["Health"]["Status"] == "healthy":
                try:
                    pools = health_client.list_user_pools(MaxResults=60)["UserPools"]
                    if not any(pool["Id"] == self.pool for pool in pools):
                        raise RuntimeError(
                            "Cognito state did not reload after backup; reset refused."
                        )
                    print(f"Validated backup: {backup}", flush=True)
                    return
                except (BotoCoreError, ClientError):
                    pass
            time.sleep(1)
        raise RuntimeError("Emulator did not become healthy after backup; reset was not started.")

    def require_backup(self):
        if not self.checked or self.backup is None:
            raise RuntimeError(
                "An explicit reset requires successful preflight and a fresh backup."
            )
        backup = self.backup.resolve()
        if not backup.is_relative_to((self.state / "backups").resolve()):
            raise RuntimeError("Backup is outside the local backup directory.")
        marker = json.loads((backup / "complete.json").read_text(encoding="utf-8"))
        if (
            marker["root"] != str(self.root)
            or marker["sha256"]
            != hashlib.sha256((backup / "database.dump").read_bytes()).hexdigest()
            or not (backup / "floci-data").is_dir()
        ):
            raise RuntimeError("Backup is incomplete or has changed; reset refused.")
