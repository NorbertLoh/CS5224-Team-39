import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from telelink_common.errors import DomainError

from app.database import create_database_engine
from app.lifecycle import can_join, ensure_session, transition
from app.models import ConsultationSession
from tests.test_lifecycle import END, START


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    if os.environ.get("CONSULTATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set CONSULTATION_TEST_ALLOW_RESET=1 for disposable data only")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        yield engine
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="consultation") == ["alembic_version"]
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT value FROM unrelated.sentinel")) == "preserve"
            assert (
                conn.scalar(text("SELECT to_regprocedure('consultation.guard_session()')")) is None
            )
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


def context():
    return dict(
        appointment_id=uuid4(),
        tenant_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        starts_at=START,
        ends_at=END,
    )


def create(engine, fields=None):
    fields = context() if fields is None else fields
    with Session(engine) as db, db.begin():
        row = ensure_session(db, **fields)
        return row.session_id, fields


def act(engine, session_id, fields, action, now):
    with Session(engine) as db, db.begin():
        row = transition(
            db,
            session_id=session_id,
            tenant_id=fields["tenant_id"],
            doctor_id=fields["doctor_id"],
            action=action,
            now=now,
        )
        return row.status, row.started_at, row.ended_at


def test_roundtrip_idempotency_and_conflicting_context(database):
    session_id, fields = create(database)
    assert create(database, fields)[0] == session_id
    for key in ("tenant_id", "patient_id", "doctor_id"):
        with pytest.raises(DomainError, match="context"):
            create(database, {**fields, key: uuid4()})
    with Session(database) as db:
        row = db.get(ConsultationSession, session_id)
        assert row.created_at.utcoffset() == timedelta(0)
        assert row.status == "scheduled" and row.started_at is None


@pytest.mark.parametrize("offset", [-600, -1, 1800, 1801])
def test_start_rejects_outside_scheduled_interval(database, offset):
    session_id, fields = create(database)
    with pytest.raises(DomainError):
        act(database, session_id, fields, "start", START + timedelta(seconds=offset))


def test_lifecycle_retries_rejoin_and_terminal_state(database):
    session_id, fields = create(database)
    with pytest.raises(DomainError):
        act(database, session_id, fields, "end", START)
    assert act(database, session_id, fields, "start", START) == ("in_progress", START, None)
    assert act(database, session_id, fields, "start", END) == ("in_progress", START, None)
    with Session(database) as db:
        row = db.get(ConsultationSession, session_id)
        assert can_join(row, now=END - timedelta(microseconds=1))
        assert can_join(row, now=END)
        assert can_join(row, now=END + timedelta(days=1))
    with pytest.raises(DomainError):
        act(database, session_id, fields, "end", START - timedelta(seconds=1))
    assert act(database, session_id, fields, "end", END) == ("completed", START, END)
    assert act(database, session_id, fields, "end", END + timedelta(days=1)) == (
        "completed",
        START,
        END,
    )
    with pytest.raises(DomainError):
        act(database, session_id, fields, "start", START)


def test_tenant_and_assigned_doctor_isolation(database):
    session_id, fields = create(database)
    for key in ("tenant_id", "doctor_id"):
        with pytest.raises(DomainError) as error:
            act(database, session_id, {**fields, key: uuid4()}, "start", START)
        assert error.value.status_code == (404 if key == "tenant_id" else 403)


def test_transaction_rollback(database):
    session_id, fields = create(database)
    with Session(database) as db:
        transition(
            db,
            session_id=session_id,
            tenant_id=fields["tenant_id"],
            doctor_id=fields["doctor_id"],
            action="start",
            now=START,
        )
        db.rollback()
        assert db.get(ConsultationSession, session_id).status == "scheduled"


def test_concurrent_creation_start_end(database):
    fields = context()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create(database, fields)[0], range(2)))
        assert ids[0] == ids[1]
        for action, now in (("start", START), ("end", END)):
            results = list(pool.map(lambda _: act(database, ids[0], fields, action, now), range(2)))
            assert results[0] == results[1]
    with Session(database) as db:
        assert (
            len(
                db.scalars(
                    select(ConsultationSession).where(
                        ConsultationSession.appointment_id == fields["appointment_id"]
                    )
                ).all()
            )
            == 1
        )


@pytest.mark.parametrize(
    "values",
    [
        {"tenant_id": uuid4()},
        {"appointment_id": uuid4()},
        {"patient_id": uuid4()},
        {"doctor_id": uuid4()},
        {"starts_at": START - timedelta(minutes=1)},
        {"ends_at": START},
        {"status": "completed", "started_at": START, "ended_at": END},
        {"status": "unknown"},
        {"started_at": START},
    ],
)
def test_database_rejects_context_changes_and_invalid_states(database, values):
    session_id, _ = create(database)
    with pytest.raises(IntegrityError), Session(database) as db, db.begin():
        db.execute(
            update(ConsultationSession)
            .where(ConsultationSession.session_id == session_id)
            .values(**values)
        )


def test_database_rejects_reopening_and_timestamp_rewrite(database):
    session_id, fields = create(database)
    act(database, session_id, fields, "start", START)
    act(database, session_id, fields, "end", END)
    for values in (
        {"ended_at": END + timedelta(seconds=1)},
        {"started_at": START + timedelta(seconds=1)},
        {"status": "in_progress", "ended_at": None},
    ):
        with pytest.raises(IntegrityError), Session(database) as db, db.begin():
            db.execute(
                update(ConsultationSession)
                .where(ConsultationSession.session_id == session_id)
                .values(**values)
            )


def test_role_cannot_write_other_service_schema(database):
    with pytest.raises(ProgrammingError), database.begin() as conn:
        conn.execute(text("UPDATE unrelated.sentinel SET value = 'changed'"))


def test_database_url_validation(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///sessions.db", "postgresql+psycopg://host", "bad"):
        with pytest.raises(ValueError):
            create_database_engine(url)


@pytest.mark.parametrize(
    "values",
    [
        {"ends_at": START},
        {"ends_at": START - timedelta(seconds=1)},
        {"patient_id": None},
        {"tenant_id": None},
        {"status": "in_progress", "started_at": START},
        {"status": "completed", "started_at": START, "ended_at": END},
    ],
)
def test_database_rejects_invalid_insert(database, values):
    with pytest.raises(IntegrityError), Session(database) as db, db.begin():
        db.add(ConsultationSession(**{**context(), **values}))
        db.flush()


def test_unique_appointment_is_global_and_participants_distinct(database):
    _, fields = create(database)
    for values in (
        {**fields, "tenant_id": uuid4()},
        {**context(), "patient_id": fields["doctor_id"], "doctor_id": fields["doctor_id"]},
    ):
        with pytest.raises(IntegrityError), Session(database) as db, db.begin():
            db.add(ConsultationSession(**values))
            db.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"status": "in_progress", "started_at": START - timedelta(microseconds=1)},
        {"status": "in_progress", "started_at": END},
    ],
)
def test_database_start_window_cannot_be_bypassed(database, values):
    session_id, _ = create(database)
    with pytest.raises(IntegrityError), Session(database) as db, db.begin():
        db.execute(
            update(ConsultationSession)
            .where(ConsultationSession.session_id == session_id)
            .values(**values)
        )


def test_database_end_cannot_precede_start(database):
    session_id, fields = create(database)
    act(database, session_id, fields, "start", START)
    with pytest.raises(IntegrityError), Session(database) as db, db.begin():
        db.execute(
            update(ConsultationSession)
            .where(ConsultationSession.session_id == session_id)
            .values(status="completed", ended_at=START - timedelta(microseconds=1))
        )


def test_start_at_last_instant_and_end_after_scheduled_end(database):
    session_id, fields = create(database)
    instant = END - timedelta(microseconds=1)
    assert act(database, session_id, fields, "start", instant)[1] == instant
    assert act(database, session_id, fields, "end", END + timedelta(minutes=10))[2] == (
        END + timedelta(minutes=10)
    )


def test_invalid_snapshot_is_not_persisted(database):
    fields = context()
    for values in (
        {"ends_at": START},
        {"starts_at": START.replace(tzinfo=None)},
        {"patient_id": fields["doctor_id"]},
    ):
        with pytest.raises(ValueError), Session(database) as db, db.begin():
            ensure_session(db, **{**fields, **values})
