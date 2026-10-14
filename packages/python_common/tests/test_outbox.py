import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from event_fixtures import APPOINTMENT, CORRELATION, TENANT
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.orm import sessionmaker

from telelink_common.events import new_event, parse_put_events_entry, to_put_events_entry
from telelink_common.outbox import (
    PublishResult,
    add_event,
    outbox_table,
    publish_pending,
    retry_delay,
)

BUS = "telelink-local"


class FakeEventBridge:
    """Records PutEvents calls; `fail` maps an entry index to its ErrorCode."""

    def __init__(self, fail=None, raises=None):
        self.calls = []
        self.fail = fail or {}
        self.raises = raises

    def put_events(self, Entries):
        self.calls.append(Entries)
        if self.raises:
            raise self.raises
        return {
            "Entries": [
                {"ErrorCode": self.fail[index], "ErrorMessage": entry["Detail"]}
                if index in self.fail
                else {"EventId": str(uuid4())}
                for index, entry in enumerate(Entries)
            ]
        }


def make_event():
    return new_event(
        "appointment_confirmed.v1",
        tenant_id=TENANT,
        correlation_id=CORRELATION,
        occurred_at=datetime(2026, 10, 12, 3, tzinfo=timezone.utc),
        data={"appointment_id": APPOINTMENT},
    )


def due():
    # Rows default to the database clock; publish slightly after it.
    return datetime.now(timezone.utc) + timedelta(seconds=1)


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'outbox.db'}")
    metadata = MetaData()
    outbox = outbox_table(metadata)
    metadata.create_all(engine)
    yield sessionmaker(engine), outbox
    engine.dispose()


def stage(store, count=1):
    sessions, outbox = store
    events = [make_event() for _ in range(count)]
    with sessions.begin() as session:
        for event in events:
            add_event(session, outbox, event)
    return events


def row(store, event):
    sessions, outbox = store
    with sessions() as session:
        return session.execute(select(outbox).where(outbox.c.event_id == event.event_id)).one()


def test_event_is_staged_only_when_the_transaction_commits(store):
    sessions, outbox = store
    with pytest.raises(RuntimeError):
        with sessions.begin() as session:
            add_event(session, outbox, make_event())
            raise RuntimeError("domain change failed")
    with sessions() as session:
        assert session.execute(select(outbox)).all() == []

    (event,) = stage(store)
    stored = row(store, event)
    assert (stored.attempts, stored.published_at, stored.last_error) == (0, None, None)


def test_publish_sends_the_original_envelope_once(store):
    sessions, outbox = store
    events = stage(store, 3)
    client = FakeEventBridge()

    result = publish_pending(sessions, outbox, client, BUS, now=due())

    assert (result.published, result.failed) == (3, 0)
    (entries,) = client.calls
    assert sorted(entries, key=lambda entry: entry["Detail"]) == sorted(
        (to_put_events_entry(event, BUS) for event in events), key=lambda entry: entry["Detail"]
    )
    assert {parse_put_events_entry(entry) for entry in entries} == set(events)
    assert all(row(store, event).published_at is not None for event in events)
    assert publish_pending(sessions, outbox, client, BUS, now=due()) == PublishResult()
    assert len(client.calls) == 1


def test_only_failed_entries_are_retried_after_backoff(store):
    sessions, outbox = store
    stage(store, 2)
    client = FakeEventBridge(fail={1: "ThrottlingException"})
    first = due()

    result = publish_pending(sessions, outbox, client, BUS, now=first)

    assert (result.published, result.failed) == (1, 1)
    failed_entry = client.calls[0][1]
    failed = row(store, parse_put_events_entry(failed_entry))
    assert (failed.attempts, failed.last_error, failed.published_at) == (
        1,
        "ThrottlingException",
        None,
    )
    assert publish_pending(sessions, outbox, client, BUS, now=first).failed == 0
    assert len(client.calls) == 1

    client.fail = {}
    retry = publish_pending(sessions, outbox, client, BUS, now=first + timedelta(seconds=5))
    assert (retry.published, retry.failed) == (1, 0)
    assert client.calls[1] == [failed_entry]
    assert row(store, parse_put_events_entry(failed_entry)).last_error is None


def test_send_errors_are_recorded_without_payload_values(store):
    sessions, outbox = store
    (event,) = stage(store)
    client = FakeEventBridge(raises=ConnectionError(f"failed sending {APPOINTMENT}"))

    result = publish_pending(sessions, outbox, client, BUS, now=due())

    assert (result.published, result.failed) == (0, 1)
    stored = row(store, event)
    assert (stored.attempts, stored.last_error) == (1, "ConnectionError")
    assert stored.published_at is None


def test_error_messages_from_eventbridge_are_not_stored(store):
    sessions, outbox = store
    (event,) = stage(store)
    publish_pending(sessions, outbox, FakeEventBridge(fail={0: "InternalFailure"}), BUS, now=due())
    assert row(store, event).last_error == "InternalFailure"


def test_mismatched_response_counts_as_failure(store):
    sessions, outbox = store
    (event,) = stage(store)

    class EmptyResponse:
        def put_events(self, Entries):
            return {"Entries": []}

    result = publish_pending(sessions, outbox, EmptyResponse(), BUS, now=due())
    assert result.failed == 1
    assert row(store, event).last_error == "InvalidResponse"


def test_batches_follow_the_put_events_limit(store):
    sessions, outbox = store
    stage(store, 12)
    client = FakeEventBridge()
    assert publish_pending(sessions, outbox, client, BUS, now=due()).published == 10
    assert publish_pending(sessions, outbox, client, BUS, now=due()).published == 2
    assert publish_pending(sessions, outbox, client, BUS, batch_size=3, now=due()).published == 0
    for bad_size in (0, 11):
        with pytest.raises(ValueError):
            publish_pending(sessions, outbox, client, BUS, batch_size=bad_size)
    with pytest.raises(ValueError, match="EVENT_BUS_NAME"):
        publish_pending(sessions, outbox, client, None)


def test_retry_delay_doubles_and_is_capped():
    assert [retry_delay(attempt).total_seconds() for attempt in range(1, 9)] == [
        5,
        10,
        20,
        40,
        80,
        160,
        300,
        300,
    ]
    assert retry_delay(1000) == timedelta(minutes=5)


@pytest.fixture
def postgres_store():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database to run integration")
    from telelink_common.database import create_postgres_engine

    engine = create_postgres_engine(url)
    with engine.connect() as connection:
        # Local setup scripts give each service role a schema with the same name.
        schema = connection.scalar(text("SELECT current_user"))
    metadata = MetaData(schema=schema)
    outbox = outbox_table(metadata, name=f"outbox_test_{uuid4().hex[:8]}")
    metadata.create_all(engine)
    try:
        yield sessionmaker(engine), outbox
    finally:
        metadata.drop_all(engine)
        engine.dispose()


def test_concurrent_publishers_skip_locked_rows(postgres_store):
    sessions, outbox = postgres_store
    stage(postgres_store, 2)
    nested = []

    class PublishesWhileLocked(FakeEventBridge):
        def put_events(self, Entries):
            # A second publisher runs while the first still holds its row locks.
            if not nested:
                nested.append(publish_pending(sessions, outbox, FakeEventBridge(), BUS))
            return super().put_events(Entries)

    client = PublishesWhileLocked()
    result = publish_pending(sessions, outbox, client, BUS, batch_size=1)

    assert result.published == 1
    assert nested[0].published == 1
    assert len(client.calls) == 1
    with sessions() as session:
        assert (
            session.scalar(select(outbox.c.event_id).where(outbox.c.published_at.is_(None))) is None
        )
