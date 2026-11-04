"""Focused offline tests for the destructive command's boundaries and import safety."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import dataset
from environment import SCHEMAS, Environment, app_origin, local_url, published_port


class SeedSafeguards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ctx = Environment(self.root, "https://localhost:8443")

    def test_external_targets_rejected(self):
        for target in [
            "https://s3.amazonaws.com",
            "http://floci:4566",
            "http://localhost.evil/",
            "file:///tmp/test",
        ]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                local_url(target, {"http"}, root_path=True)

    def test_aws_path_query_and_fragment_rejected(self):
        for suffix in ["/proxy", "?target=production", "#endpoint"]:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                local_url("http://localhost:4566" + suffix, {"http"}, root_path=True)

    def test_app_origin_validation(self):
        self.assertEqual(app_origin("https://my-host.demo.ts.net/"), "https://my-host.demo.ts.net")
        self.assertEqual(app_origin("http://localhost:5173"), "http://localhost:5173")
        for value in [
            "https://example.com",
            "http://host.demo.ts.net",
            "https://user:secret@localhost",
            "https://localhost/path",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                app_origin(value)

    def test_docker_published_port_must_match(self):
        container = {
            "NetworkSettings": {
                "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55411"}]}
            },
            "State": {"Running": True},
        }
        published_port(container, 5432, 55411)
        with self.assertRaises(ValueError):
            published_port(container, 5432, 5432)
        container["State"]["Running"] = False
        with self.assertRaises(ValueError):
            published_port(container, 5432, 55411)

    def test_external_delivery_paths_rejected(self):
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ctx.local_file(outside)

    def test_reset_rejects_missing_preflight_or_backup(self):
        with self.assertRaises(RuntimeError):
            self.ctx.require_backup()
        self.ctx.checked = True
        with self.assertRaises(RuntimeError):
            self.ctx.require_backup()

    def backup(self):
        self.ctx.checked = True
        backup = self.ctx.state / "backups/test"
        backup.mkdir(parents=True)
        (backup / "floci-data").mkdir()
        data = b"PGDMP" + b"test backup" * 200
        (backup / "database.dump").write_bytes(data)
        (backup / "complete.json").write_text(
            json.dumps({"root": str(self.ctx.root), "sha256": hashlib.sha256(data).hexdigest()}),
            encoding="utf-8",
        )
        self.ctx.backup = backup
        return backup

    def test_complete_backup_accepted(self):
        self.backup()
        self.ctx.require_backup()

    def test_tampered_backup_rejected(self):
        backup = self.backup()
        (backup / "database.dump").write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            self.ctx.require_backup()

    def test_other_checkout_backup_rejected(self):
        backup = self.backup()
        marker = json.loads((backup / "complete.json").read_text())
        marker["root"] = "another-checkout"
        (backup / "complete.json").write_text(json.dumps(marker))
        with self.assertRaises(RuntimeError):
            self.ctx.require_backup()

    def test_import_and_failed_backup_guard_do_not_touch_aws(self):
        ctx = SimpleNamespace(
            root=self.root,
            state=self.ctx.state,
            origin=self.ctx.origin,
            aws_options={},
            admin=MagicMock(),
            require_backup=MagicMock(side_effect=RuntimeError("no backup")),
        )
        with patch.object(dataset.boto3, "client") as client:
            with self.assertRaises(RuntimeError):
                dataset.seed(ctx)
            client.assert_not_called()
            ctx.admin.assert_not_called()

    def fixtures(self):
        (self.root / "dev").mkdir()
        (self.root / "dev/local_stack.ps1").touch()
        for service in SCHEMAS:
            directory = self.root / f"services/{service}"
            directory.mkdir(parents=True)
            values = [
                "SERVICE_ENVIRONMENT=local",
                f"SERVICE_DATABASE_URL=postgresql+psycopg://{service}:test@127.0.0.1:55411/telelink",
                "SERVICE_AWS_ENDPOINT_URL=http://localhost:4566",
            ]
            if service == "scheduling":
                values.append("SERVICE_REDIS_URL=redis://127.0.0.1:6379/0")
            (directory / ".env").write_text("\n".join(values), encoding="utf-8")
        interpreter = self.root / "services/document/.venv/Scripts/python.exe"
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
        (self.root / "apps/web").mkdir(parents=True)
        (self.root / "apps/web/.env").write_text(
            "VITE_USE_AWS=false\nVITE_COGNITO_CLIENT_ID=demo-client\n", encoding="utf-8"
        )

    def inspect(self, name):
        service = "postgres" if "postgres" in name else "floci" if "floci" in name else "redis"
        internal, external = {
            "postgres": (5432, 55411),
            "floci": (4566, 4566),
            "redis": (6379, 6379),
        }[service]
        return {
            "Config": {
                "Image": {
                    "postgres": "postgres:17",
                    "floci": "floci/floci:2.2.0",
                    "redis": "redis:7.4-alpine",
                }[service],
                "Env": ["POSTGRES_PASSWORD=test"],
            },
            "State": {"Running": True},
            "NetworkSettings": {
                "Ports": {f"{internal}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(external)}]}
            },
            "Mounts": [{"Destination": "/app/data"}],
        }

    def test_preflight_is_read_only(self):
        self.fixtures()
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value = [(s,) for s in SCHEMAS]
        client = MagicMock()
        client.list_user_pools.return_value = {
            "UserPools": [{"Name": "telelink-local", "Id": "demo-pool"}]
        }
        client.describe_user_pool_client.return_value = {
            "UserPoolClient": {"ExplicitAuthFlows": ["ALLOW_USER_PASSWORD_AUTH"]}
        }
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("environment.inspect_container", side_effect=self.inspect),
            patch("environment.docker", return_value="") as docker,
            patch("environment.boto3.client", return_value=client),
            patch("environment.psycopg.connect", return_value=connection),
        ):
            self.ctx.preflight()
        self.assertTrue(self.ctx.checked)
        self.assertFalse(self.ctx.state.exists())
        self.assertEqual(docker.call_args.args[0], "ps")
        client.admin_delete_user.assert_not_called()
        client.admin_create_user.assert_not_called()

    def test_nonlocal_environment_rejected_before_docker(self):
        self.fixtures()
        path = self.root / "services/identity/.env"
        path.write_text(
            path.read_text().replace("SERVICE_ENVIRONMENT=local", "SERVICE_ENVIRONMENT=production")
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("environment.inspect_container") as inspect,
        ):
            with self.assertRaises(ValueError):
                self.ctx.preflight()
            inspect.assert_not_called()

    def test_environment_overrides_rejected(self):
        with (
            patch.dict("os.environ", {"SERVICE_DATABASE_URL": "postgresql://production"}),
            self.assertRaises(ValueError),
        ):
            self.ctx.preflight()


if __name__ == "__main__":
    unittest.main()
