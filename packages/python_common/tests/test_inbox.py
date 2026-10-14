import json
import logging
import os
from uuid import uuid4

import pytest
from event_fixtures import FIXTURES, sqs_body
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from telelink_common.events import parse_put_events_entry
from telelink_common.inbox import ConsumeResult, consume_batch, inbox_table

CONSUMER = "scheduling"
PAYMENT = FIXTURES[0]  # consultation_payment_succeeded.v1, routed to scheduling
QUEUE = "http://floci:4566/000000000000/telelink-local-scheduling"


class FakeSQS:
    """Serves queued bodies once each and records deleted receipt handles."""

    def __init__(self, *bodies, fail_delete=False):
        self.bodies = list(bodies)
        self.deleted = []
        self.fail_delete = fail_delete

    def receive_message(self, QueueUrl, MaxNumberOfMessages, WaitTimeSeconds):
        batch, self.bodies = self.bodies[:MaxNumberOfMessages], self.bodies[MaxNumberOfMessages:]
        return {"Messages": [{"Body": body, "ReceiptHandle": str(uuid4())} for body in batch]}

    def delete_message(self, QueueUrl, ReceiptHandle):
        if self.fail_delete:
            raise ConnectionError("delete failed")
        self.deleted.append(ReceiptHandle)


class Store:
    def __init__(self, engine, schema=None, suffix=""):
        self.engine = engine
        self.metadata = MetaData(schema=schema)
        self.inbox = inbox_table(self.metadata, name=f"event_inbox{suffix}")
        # Stands in for the consumer's own domain table.
        self.effects = Table(
            f"effects{suffix}", self.metadata, Column("event_id", Uuid, primary_key=True)
        )
        self.metadata.create_all(engine)
        self.sessions = sessionmaker(engine)

    def count(self, table):
        with self.sessions() as session:
            return session.scalar(select(func.count()).select_from(table))

    def consume(self, sqs, handler=None):
        return consume_batch(
            self.sessions, self.inbox, sqs, QUEUE, CONSUMER, handler or self.record, wait_seconds=0
        )

    def record(self, session, event):
        session.execute(self.effects.insert().values(event_id=event.event_id))


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'inbox.db'}")
        yield Store(engine)
        engine.dispose()
        return
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database to run integration")
    from telelink_common.database import create_postgres_engine

    engine = create_postgres_engine(url)
    with engine.connect() as connection:
        # Local setup scripts give each service role a schema with the same name.
        schema = connection.scalar(text("SELECT current_user"))
    store = Store(engine, schema=schema, suffix=f"_test_{uuid4().hex[:8]}")
    try:
        yield store
    finally:
        store.metadata.drop_all(engine)
        engine.dispose()


def test_event_is_handled_recorded_and_acknowledged(store):
    sqs = FakeSQS(sqs_body(PAYMENT))
    handled = []

    def handler(session, event):
        handled.append(event)
        store.record(session, event)

    assert store.consume(sqs, handler) == ConsumeResult(processed=1)
    assert handled == [parse_put_events_entry(PAYMENT)]
    assert len(sqs.deleted) == 1
    with store.sessions() as session:
        row = session.execute(select(store.inbox)).one()
    assert (row.consumer, row.event_id, row.detail_type) == (
        CONSUMER,
        handled[0].event_id,
        "consultation_payment_succeeded.v1",
    )
    assert row.processed_at is not None


def test_duplicate_delivery_is_acknowledged_without_handling_again(store):
    sqs = FakeSQS(sqs_body(PAYMENT), sqs_body(PAYMENT, id="redelivered"))
    assert store.consume(sqs) == ConsumeResult(processed=1, duplicates=1)
    assert len(sqs.deleted) == 2
    assert store.count(store.effects) == 1


def test_handler_failure_rolls_back_and_leaves_the_message(store):
    def failing(session, event):
        store.record(session, event)
        raise RuntimeError("domain rule failed")

    sqs = FakeSQS(sqs_body(PAYMENT))
    assert store.consume(sqs, failing) == ConsumeResult(failed=1)
    assert sqs.deleted == []
    assert store.count(store.inbox) == store.count(store.effects) == 0

    # Redelivery after the visibility timeout succeeds once the cause is fixed.
    sqs.bodies.append(sqs_body(PAYMENT))
    assert store.consume(sqs) == ConsumeResult(processed=1)
    assert store.count(store.effects) == 1


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        sqs_body(FIXTURES[2]),  # appointment_confirmed.v1 is routed to notification only
        sqs_body(PAYMENT, source="telelink.document"),
        sqs_body(PAYMENT, detail={**json.loads(PAYMENT["Detail"]), "schema_version": 2}),
    ],
)
def test_invalid_or_misrouted_messages_are_never_acknowledged(store, body):
    sqs = FakeSQS(body)
    assert store.consume(sqs) == ConsumeResult(failed=1)
    assert sqs.deleted == []
    assert store.count(store.inbox) == 0


def test_one_bad_message_does_not_block_the_batch(store):
    sqs = FakeSQS("not json", sqs_body(PAYMENT))
    assert store.consume(sqs) == ConsumeResult(processed=1, failed=1)
    assert len(sqs.deleted) == 1


def test_failed_delete_is_retried_as_a_duplicate(store):
    sqs = FakeSQS(sqs_body(PAYMENT), fail_delete=True)
    assert store.consume(sqs) == ConsumeResult(processed=1)
    sqs.fail_delete = False
    sqs.bodies.append(sqs_body(PAYMENT))
    assert store.consume(sqs) == ConsumeResult(duplicates=1)
    assert store.count(store.effects) == 1


def test_failure_logs_do_not_include_payload_values(store, caplog):
    secret = "patient@example.com"

    def failing(session, event):
        raise RuntimeError(f"cannot email {secret}")

    with caplog.at_level(logging.WARNING, logger="telelink.inbox"):
        store.consume(FakeSQS(sqs_body(PAYMENT)), failing)
    (record,) = caplog.records
    assert record.getMessage() == "inbox_message_failed"
    assert record.exc_info[0] is RuntimeError


def test_consumer_and_batch_size_are_validated(store):
    sqs = FakeSQS()
    with pytest.raises(ValueError, match="unknown consumer"):
        consume_batch(store.sessions, store.inbox, sqs, QUEUE, "billing", store.record)
    for bad_size in (0, 11):
        with pytest.raises(ValueError):
            consume_batch(
                store.sessions,
                store.inbox,
                sqs,
                QUEUE,
                CONSUMER,
                store.record,
                max_messages=bad_size,
            )
