"""AWS reset boundary checks; never connect to AWS or the running demo."""

import importlib.util
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from requested_seed import ACCOUNTS, licence_pdf

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "aws_reset", ROOT / "infra/modules/demo-platform/reset_demo.py"
)
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)
CONFIG = {
    "deployment": "demo",
    "pool": "ap-southeast-1_demo",
    "account": "123456789012",
    "seed_secret": "seed",
    "master_secret": "master",
    "db_host": "demo.rds.amazonaws.com",
}
SEED = {"patient_phone": "81234567", "new_account_password": "DemoOnlyPassword1!"}


class Connection:
    def __init__(self):
        self.queries = []
        self.rollbacks = 0

    def execute(self, query, params=None):
        value = query if isinstance(query, str) else query.as_string()
        self.queries.append(value)
        row = (True,) if "pg_try_advisory_lock" in value or "rolcanlogin" in value else ("0001",)
        if "FROM pg_auth_members" in value:
            row = None
        return Mock(fetchone=lambda: row)

    @contextmanager
    def transaction(self):
        try:
            yield
        except Exception:
            self.rollbacks += 1
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class AwsResetTests(unittest.TestCase):
    def job(self):
        clients = {"sts": Mock()}
        clients["sts"].get_caller_identity.return_value = {"Account": CONFIG["account"]}
        job = reset.ResetJob(CONFIG, str(uuid4()), clients)
        job.secret = lambda arn: (
            SEED if arn == "seed" else {"username": "admin", "password": "private"}
        )
        job.read = lambda: ({"status": "queued"}, "etag")
        job.update = Mock()
        job.users = Mock(return_value={})
        job.clear_queues = Mock()
        job.clear_redis = Mock()
        return job

    def test_invalid_seed_refused_before_database_access(self):
        for config, seed in [
            ({**CONFIG, "deployment": "production"}, SEED),
            ({**CONFIG, "pool": "wrong-region"}, SEED),
            (CONFIG, {**SEED, "patient_phone": "+12025550100"}),
            (CONFIG, {**SEED, "new_account_password": ""}),
        ]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                reset.validate_config(config, seed)

    def test_success_restores_login_and_revokes_temporary_access(self):
        job, connection = self.job(), Connection()
        with (
            patch.object(reset.psycopg, "connect", return_value=connection),
            patch.object(reset.time, "sleep"),
            patch.object(reset, "seed_database") as seed,
        ):
            job.run()
        seed.assert_called_once()
        self.assertEqual(sum(" NOLOGIN" in q for q in connection.queries), 9)
        self.assertEqual(sum(" LOGIN" in q for q in connection.queries), 9)
        self.assertEqual(sum(q.startswith("REVOKE") for q in connection.queries), 9)
        self.assertEqual(job.update.call_args.args[0], "succeeded")

    def test_failed_seed_rolls_back_and_restores_all_service_logins(self):
        job, connection = self.job(), Connection()
        with (
            patch.object(reset.psycopg, "connect", return_value=connection),
            patch.object(reset.time, "sleep"),
            patch.object(reset, "seed_database", side_effect=ValueError("bad seed")),
            self.assertRaises(ValueError),
        ):
            job.run()
        self.assertEqual(connection.rollbacks, 1)
        self.assertEqual(sum(" LOGIN" in q for q in connection.queries), 9)
        self.assertNotEqual(job.update.call_args.args[0], "succeeded")
        job.clear_redis.assert_not_called()

    def test_queue_failure_prevents_database_replacement(self):
        job, connection = self.job(), Connection()
        job.clear_queues.side_effect = RuntimeError("queue not empty")
        with (
            patch.object(reset.psycopg, "connect", return_value=connection),
            patch.object(reset.time, "sleep"),
            patch.object(reset, "seed_database") as seed,
            self.assertRaises(RuntimeError),
        ):
            job.run()
        seed.assert_not_called()
        self.assertEqual(sum(" LOGIN" in q for q in connection.queries), 9)

    def test_existing_cognito_users_keep_passwords_and_subject_ids(self):
        cognito = Mock()
        subjects = {email: uuid4() for email, _, _ in ACCOUNTS}
        cognito.admin_get_user.side_effect = lambda **kw: {
            "UserAttributes": [
                {"Name": "sub", "Value": kw["Username"]},
                {"Name": "email", "Value": kw["Username"]},
                {"Name": "email_verified", "Value": "true"},
            ],
            "Enabled": True,
            "UserStatus": "CONFIRMED",
        }
        connection = Mock()
        connection.execute.side_effect = lambda query, params: Mock(
            fetchone=lambda: (subjects[params[0]],)
        )
        job = reset.ResetJob(CONFIG, str(uuid4()), {"cognito-idp": cognito})
        job.read = lambda: ({"actor_id": str(subjects["platform@example.test"])}, "etag")
        users = job.users(connection, SEED["new_account_password"])
        self.assertEqual({email: user["subject_id"] for email, user in users.items()}, subjects)
        cognito.admin_create_user.assert_not_called()
        cognito.admin_set_user_password.assert_not_called()

    def test_shared_evidence_is_a_repeatable_pdf(self):
        self.assertEqual(licence_pdf(), licence_pdf())
        self.assertTrue(licence_pdf().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
