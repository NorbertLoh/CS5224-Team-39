"""Only the explicitly opted-in disposable database is migrated/reset."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from telelink_common.database import create_postgres_engine

ROOT = Path(__file__).resolve().parents[1]


def migrate(url, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *arguments],
        cwd=ROOT,
        env=os.environ | {"SERVICE_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("BILLING_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set BILLING_TEST_ALLOW_RESET=1: tests downgrade/delete billing data")
    return url


@pytest.fixture(scope="session")
def database(database_url):
    result = migrate(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_postgres_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
