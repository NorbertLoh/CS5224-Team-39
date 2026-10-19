from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
import test_persistence
from sqlalchemy import delete, select
from sqlalchemy import event as sql_event
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.events import new_event
from telelink_common.inbox import consume_batch, handle_event

from app.dispatch import dispatch_one, recover_stale
from app.email import EmailSendError
from app.intake import QueueNotification
from app.models import NotificationJob, event_inbox
from app.recipients import Recipient, RecipientLookupError
from app.settings import Settings

database = test_persistence.database


@pytest.fixture
def work(database):
    sessions = sessionmaker(database, expire_on_commit=False)
    with sessions.begin() as session:
        session.execute(delete(NotificationJob))
        session.execute(delete(event_inbox))
    yield sessions
    with sessions.begin() as session:
        session.execute(delete(NotificationJob))
        session.execute(delete(event_inbox))


def config(**changes):
    return Settings(
        _env_file=None,
        email_sender="notifications@telelink.test",
        app_url="http://localhost:5173",
        **changes,
    )


def workflow(kind="appointment_confirmed.v1"):
    data = {"appointment_id": uuid4()}
    if kind == "document_ready.v1":
        data |= {"document_id": uuid4(), "prescription_id": uuid4()}
    if kind == "delivery_status_changed.v1":
        data = {"order_id": uuid4(), "delivery_id": uuid4(), "status": "submitted"}
    return new_event(
        kind,
        tenant_id=uuid4(),
        correlation_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        data=data,
    )


class Directory:
    def __init__(self):
        self.calls = 0

    def resolve(self, event):
        self.calls += 1
        return Recipient(uuid4(), "patient@example.test")


class Sender:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def send(self, recipient, message):
        self.calls += 1
        if self.error:
            raise self.error
        return "accepted-local"


def queue(work, event=None, directory=None):
    value = event or workflow()
    handle_event(
        work, event_inbox, "notification", value, QueueNotification(directory or Directory())
    )
    return value


def rows(work):
    with work() as session:
        return list(session.scalars(select(NotificationJob)))


@pytest.mark.parametrize(
    "kind", ["appointment_confirmed.v1", "document_ready.v1", "delivery_status_changed.v1"]
)
def test_duplicate_event_is_one_job_and_send(work, kind):
    directory = Directory()
    value = queue(work, workflow(kind), directory)
    assert not handle_event(work, event_inbox, "notification", value, QueueNotification(directory))
    assert directory.calls == 1
    sender = Sender()
    assert dispatch_one(work, sender, config())
    assert not dispatch_one(work, sender, config())
    # Recreated dispatcher state does not resend after acceptance.
    assert not dispatch_one(sessionmaker(work.kw["bind"]), sender, config())
    row = rows(work)[0]
    assert (
        row.status == "sent" and row.attempts == 1 and row.provider_message_id == "accepted-local"
    )
    assert sender.calls == 1


def test_lookup_failure_rolls_back_inbox_and_job(work):
    class Broken:
        def resolve(self, value):
            raise RecipientLookupError("unavailable")

    value = workflow()
    with pytest.raises(RecipientLookupError):
        queue(work, value, Broken())
    assert rows(work) == []
    with work() as session:
        assert session.scalar(select(event_inbox.c.event_id)) is None
    queue(work, value)
    assert len(rows(work)) == 1


def test_stale_event_acknowledged_without_job(work):
    class Stale:
        def resolve(self, value):
            return None

    queue(work, directory=Stale())
    assert rows(work) == []
    with work() as session:
        assert session.scalar(select(event_inbox.c.event_id)) is not None


def test_throttle_bounded_retry_and_persistent_failure(work):
    queue(work)
    sender = Sender(EmailSendError(definitive=True, retryable=True))
    settings = config(send_max_attempts=2)
    assert dispatch_one(work, sender, settings)
    row = rows(work)[0]
    assert row.status == "failed" and row.error_code == "ses_rejected" and row.ready_at
    assert not dispatch_one(work, sender, settings)
    with work.begin() as session:
        session.get(NotificationJob, row.job_id).ready_at = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
    assert dispatch_one(work, sender, settings)
    row = rows(work)[0]
    assert row.attempts == 2 and row.ready_at is None and sender.calls == 2
    assert not dispatch_one(work, sender, settings)


@pytest.mark.parametrize(
    "error,status",
    [
        (EmailSendError(definitive=True), "failed"),
        (EmailSendError(), "uncertain"),
        (RuntimeError("private error"), "uncertain"),
    ],
)
def test_non_retryable_and_ambiguous_are_not_resent(work, error, status):
    queue(work)
    sender = Sender(error)
    dispatch_one(work, sender, config())
    assert rows(work)[0].status == status
    assert rows(work)[0].ready_at is None
    assert not dispatch_one(work, sender, config())
    assert sender.calls == 1


def test_crash_during_send_becomes_uncertain(work):
    queue(work)
    sender = Sender(SystemExit())
    with pytest.raises(SystemExit):
        dispatch_one(work, sender, config())
    row = rows(work)[0]
    assert row.status == "sending"
    assert recover_stale(work, config()) == 0
    with work.begin() as session:
        session.get(NotificationJob, row.job_id).send_started_at = datetime.now(
            timezone.utc
        ) - timedelta(minutes=10)
    assert recover_stale(work, config()) == 1
    assert rows(work)[0].status == "uncertain"
    assert not dispatch_one(work, sender, config())


def test_acceptance_commit_failure_does_not_resend(work):
    queue(work)
    sender = Sender()

    def fail_commit(session):
        if any(isinstance(row, NotificationJob) and row.status == "sent" for row in session.dirty):
            raise RuntimeError("simulated database failure after SES acceptance")

    sql_event.listen(Session, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError):
            dispatch_one(work, sender, config())
    finally:
        sql_event.remove(Session, "before_commit", fail_commit)
    assert rows(work)[0].status == "sending"
    assert not dispatch_one(work, sender, config())
    assert sender.calls == 1


def test_concurrent_dispatchers_send_once(work):
    queue(work)
    started, release = Event(), Event()

    class Blocking(Sender):
        def send(self, recipient, message):
            started.set()
            assert release.wait(5)
            return super().send(recipient, message)

    sender = Blocking()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(dispatch_one, work, sender, config())
        assert started.wait(5)
        try:
            assert not dispatch_one(work, sender, config())
        finally:
            release.set()
        assert first.result(timeout=5)
    assert sender.calls == 1


def test_sqs_delete_failure_replay_after_commit(work):
    import json

    value = workflow()
    body = json.dumps(
        {"source": value.source, "detail-type": value.detail_type, "detail": value.detail()}
    )

    class SQS:
        def receive_message(self, **kwargs):
            return {"Messages": [{"Body": body, "ReceiptHandle": "handle"}]}

        def delete_message(self, **kwargs):
            raise RuntimeError("simulated delete failure")

    directory = Directory()
    result = consume_batch(
        work,
        event_inbox,
        SQS(),
        "queue",
        "notification",
        QueueNotification(directory),
        wait_seconds=0,
    )
    assert result.processed == 1
    result = consume_batch(
        work,
        event_inbox,
        SQS(),
        "queue",
        "notification",
        QueueNotification(directory),
        wait_seconds=0,
    )
    assert result.duplicates == 1 and directory.calls == 1 and len(rows(work)) == 1
