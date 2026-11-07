"""Real migrated-schema checks, restricted to an explicitly disposable test DB."""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from requested_seed import ACCOUNTS, licence_pdf
from test_aws_reset import reset

URL = os.environ.get("RESET_TEST_DATABASE_URL", "")
ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(URL, "Set RESET_TEST_DATABASE_URL for disposable PostgreSQL seed checks")
class ResetDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = urlsplit(URL)
        if target.hostname not in {"127.0.0.1", "localhost"} or target.path != "/rf57_reset_test":
            raise ValueError("Only the dedicated loopback rf57_reset_test database is allowed")
        cls.connection = psycopg.connect(URL, autocommit=True)
        cls.users = {
            email: {"subject_id": uuid4(), "sub": str(uuid4())} for email, _, _ in ACCOUNTS
        }
        with cls.connection.transaction():
            cls.connection.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
            for schema in reset.SCHEMAS:
                cls.connection.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
                )
        for schema in reset.SCHEMAS:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "services" / schema,
                env={
                    **os.environ,
                    "SERVICE_DATABASE_URL": URL.replace(
                        "postgresql://", "postgresql+psycopg://", 1
                    ),
                },
                check=True,
                capture_output=True,
                text=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def markers(self):
        return {
            schema: self.connection.execute(
                sql.SQL("SELECT version_num FROM {}.alembic_version").format(sql.Identifier(schema))
            ).fetchone()[0]
            for schema in reset.SCHEMAS
        }

    def seed(self, evidence=None):
        with self.connection.transaction():
            reset.seed_database(
                self.connection,
                self.users,
                "+6581234567",
                licence_pdf() if evidence is None else evidence,
            )

    def test_repeatable_five_accounts_two_pending_applications(self):
        before = self.markers()
        for _ in range(2):
            self.seed()
            c = self.connection
            self.assertEqual(c.execute("SELECT count(*) FROM identity.subjects").fetchone()[0], 5)
            self.assertEqual(
                c.execute(
                    "SELECT slug, status, consultation_price_minor FROM tenant.clinics"
                ).fetchone(),
                ("meridian-health-partners", "pending_review", 3000),
            )
            self.assertEqual(
                c.execute("SELECT legal_name, status FROM identity.doctor_applications").fetchone(),
                ("Dr. Tan", "pending"),
            )
            self.assertEqual(
                c.execute("SELECT count(*) FROM identity.patient_profiles").fetchone()[0], 2
            )
            self.assertEqual(
                c.execute("SELECT count(*) FROM identity.memberships").fetchone()[0], 2
            )
            for schema, table in [("scheduling", "appointments"), ("document", "documents")]:
                self.assertEqual(
                    c.execute(
                        sql.SQL("SELECT count(*) FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(table)
                        )
                    ).fetchone()[0],
                    0,
                )
            self.assertEqual(self.markers(), before)

    def test_constraint_failure_rolls_back_the_entire_replacement(self):
        self.seed()
        extra = uuid4()
        self.connection.execute(
            "INSERT INTO identity.subjects (subject_id,cognito_sub,display_name,email) "
            "VALUES (%s,%s,'Extra', 'extra@example.test')",
            (extra, str(extra)),
        )
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.seed(evidence=b"")
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM identity.subjects").fetchone()[0], 6
        )
        self.assertEqual(
            self.connection.execute("SELECT status FROM identity.doctor_applications").fetchone()[
                0
            ],
            "pending",
        )
        self.seed()

    def test_external_foreign_key_blocks_reset_instead_of_cascading(self):
        self.seed()
        self.connection.execute(
            "CREATE TABLE public.rf57_guard (subject_id uuid REFERENCES identity.subjects)"
        )
        try:
            self.connection.execute(
                "INSERT INTO public.rf57_guard SELECT subject_id FROM identity.subjects LIMIT 1"
            )
            with self.assertRaises(psycopg.errors.FeatureNotSupported):
                self.seed()
            self.assertEqual(
                self.connection.execute("SELECT count(*) FROM public.rf57_guard").fetchone()[0], 1
            )
            self.assertEqual(
                self.connection.execute("SELECT count(*) FROM identity.subjects").fetchone()[0], 5
            )
        finally:
            self.connection.execute("DROP TABLE public.rf57_guard")

    def test_worker_restores_actual_database_roles(self):
        self.seed()
        for owner in reset.SCHEMAS:
            if not self.connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (owner,)
            ).fetchone():
                self.connection.execute(
                    sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(owner))
                )
        client = Mock()
        client.get_caller_identity.return_value = {"Account": "123456789012"}
        client.admin_get_user.side_effect = lambda **kw: {
            "UserAttributes": [
                {"Name": "sub", "Value": self.users[kw["Username"]]["sub"]},
                {"Name": "email", "Value": kw["Username"]},
                {"Name": "email_verified", "Value": "true"},
            ],
            "Enabled": True,
            "UserStatus": "CONFIRMED",
        }
        config = {
            "deployment": "demo",
            "pool": "ap-southeast-1_demo",
            "account": "123456789012",
            "db_host": "127.0.0.1",
            "seed_secret": "seed",
            "master_secret": "master",
        }
        job = reset.ResetJob(config, str(uuid4()), {"sts": client, "cognito-idp": client})
        job.secret = lambda arn: (
            {"patient_phone": "81234567", "new_account_password": "TestPassword1!"}
            if arn == "seed"
            else {"username": "postgres", "password": ""}
        )
        job.read = lambda: (
            {
                "status": "queued",
                "actor_id": str(self.users["platform@example.test"]["subject_id"]),
            },
            "etag",
        )
        job.update = Mock()
        job.clear_queues, job.clear_redis = Mock(), Mock()
        connect = psycopg.connect
        with (
            patch.object(
                reset.psycopg, "connect", side_effect=lambda **kw: connect(URL, autocommit=True)
            ),
            patch.object(reset.time, "sleep"),
        ):
            job.run()
        self.assertEqual(job.update.call_args.args[0], "succeeded")
        roles = self.connection.execute(
            "SELECT rolcanlogin FROM pg_roles WHERE rolname=ANY(%s)", (list(reset.SCHEMAS),)
        ).fetchall()
        self.assertEqual(roles, [(True,)] * 9)
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM identity.subjects").fetchone()[0], 5
        )


if __name__ == "__main__":
    unittest.main()
