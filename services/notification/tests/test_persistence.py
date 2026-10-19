import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import NotificationJob


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("NOTIFICATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set NOTIFICATION_TEST_ALLOW_RESET=1 for disposable schema reset")
    previous = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    before = inspect(engine).get_table_names(schema="public")
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        yield engine
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="notification") == ["alembic_version"]
        assert inspect(engine).get_table_names(schema="public") == before
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = previous


def values(**overrides):
    return (
        dict(
            tenant_id=uuid4(),
            event_id=uuid4(),
            recipient_id=uuid4(),
            recipient_email="patient@example.test",
            template="booking_confirmed",
        )
        | overrides
    )


def insert(engine, fields):
    with Session(engine) as session, session.begin():
        row = NotificationJob(**fields)
        session.add(row)
        session.flush()
        return row.job_id


def test_defaults_and_duplicate_key(database):
    fields = values()
    key = insert(database, fields)
    with Session(database) as session:
        row = session.get(NotificationJob, key)
        assert row.status == "pending" and row.attempts == 0
        assert row.created_at.utcoffset().total_seconds() == 0
    with pytest.raises(IntegrityError):
        insert(database, fields)
    insert(database, fields | {"recipient_id": uuid4()})
    insert(database, fields | {"template": "document_ready"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "unknown"},
        {"error_code": "private provider response"},
        {"template": "unknown"},
        {"attempts": -1},
        {"status": "sent"},
        {"recipient_email": ""},
        {"recipient_email": "a@example.test\n"},
        {"provider_message_id": "orphan"},
        {"tenant_id": None},
        {"event_id": None},
        {"recipient_id": None},
    ],
)
def test_constraints(database, overrides):
    with pytest.raises(IntegrityError):
        insert(database, values(**overrides))


def test_sent_acceptance_metadata(database):
    key = insert(
        database,
        values(
            status="sent",
            attempts=1,
            provider_message_id="ses-123",
            sent_at=datetime.now(timezone.utc),
        ),
    )
    with Session(database) as session:
        assert session.get(NotificationJob, key).provider_message_id == "ses-123"


def test_failed_job(database):
    insert(database, values(status="failed", attempts=1, error_code="ses_unconfirmed"))
