"""Issuance atomicity/idempotency over HTTP and the real PostgreSQL outbox."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.events import parse_put_events_entry
from telelink_common.outbox import publish_pending
from test_api import PREFIX, body, create
from test_api import api as api
from test_api import database as database

from app.models import Prescription, PrescriptionItem, event_outbox
from app.services.issuance import issuance_event_id


def outbox_row(engine, prescription_id):
    with engine.connect() as connection:
        return connection.execute(
            select(event_outbox).where(
                event_outbox.c.event_id == issuance_event_id(prescription_id)
            )
        ).one_or_none()


def issue_url(row):
    return PREFIX + "/prescriptions/" + row["prescription_id"] + "/issue"


def test_issue_freezes_and_stages_exactly_one_metadata_event(api):
    client, state, _, appointment, medication, engine, _ = api
    draft = create(api)
    first = client.post(issue_url(draft))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "issued" and first.json()["issued_at"]
    stored = outbox_row(engine, draft["prescription_id"])
    assert stored.published_at is None and stored.attempts == 0
    envelope = parse_put_events_entry(
        {
            "Source": stored.source,
            "DetailType": stored.detail_type,
            "Time": stored.event_time,
            "Detail": stored.detail,
        }
    )
    assert envelope.source == "telelink.clinical-records"
    assert envelope.detail_type == "prescription_issued.v1"
    assert envelope.tenant_id == appointment.tenant_id
    assert envelope.correlation_id == appointment.appointment_id
    assert envelope.data.appointment_id == appointment.appointment_id
    assert str(envelope.data.prescription_id) == draft["prescription_id"]
    assert json.loads(stored.detail)["occurred_at"] == first.json()["issued_at"]
    assert set(json.loads(stored.detail)) == {
        "event_id",
        "schema_version",
        "occurred_at",
        "tenant_id",
        "correlation_id",
        "data",
    }
    assert set(json.loads(stored.detail)["data"]) == {"prescription_id", "appointment_id"}
    assert "Synthetic instructions" not in stored.detail
    assert "Synthetic medicine" not in stored.detail
    # A retry returns the same result even if catalogue availability changed afterward.
    state["catalogue_status"] = 503
    assert client.post(issue_url(draft), json={}).json() == first.json()
    assert outbox_row(engine, draft["prescription_id"]).detail == stored.detail
    assert (
        client.patch(
            PREFIX + "/prescriptions/" + draft["prescription_id"], json=body(medication)
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "user", ["patient", "other_patient", "other_doctor", "cross_tenant", "admin", "platform"]
)
def test_unauthorized_issue_never_changes_draft(api, user):
    client, state, _, _, _, engine, _ = api
    draft = create(api)
    state["user"] = user
    assert client.post(issue_url(draft)).status_code == 404
    assert outbox_row(engine, draft["prescription_id"]) is None
    with Session(engine) as session:
        assert session.get(Prescription, UUID(draft["prescription_id"])).status == "draft"


def test_completed_or_revoked_doctor_cannot_issue_or_replay(api):
    client, state, users, appointment, _, engine, _ = api
    draft = create(api)
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    assert client.post(issue_url(draft)).status_code == 409
    assert outbox_row(engine, draft["prescription_id"]) is None
    state["appointment"] = appointment
    assert client.post(issue_url(draft)).status_code == 200
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    assert client.post(issue_url(draft)).status_code == 409
    state["appointment"] = appointment
    users["doctor"].memberships[0].__dict__["status"] = "revoked"
    assert client.post(issue_url(draft)).status_code == 404


@pytest.mark.parametrize(
    "case", ["inactive", "outage", "empty", "voided", "tampered_body", "wrong_context"]
)
def test_invalid_issue_rolls_back(api, case):
    client, state, _, appointment, _, engine, _ = api
    draft = create(api)
    expected = 409
    if case == "inactive":
        state["active"] = False
    elif case == "outage":
        state["catalogue_status"] = 503
        expected = 503
    elif case == "empty":
        with engine.begin() as connection:
            connection.execute(
                delete(PrescriptionItem).where(
                    PrescriptionItem.prescription_id == UUID(draft["prescription_id"])
                )
            )
    elif case == "voided":
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE clinical_records.prescriptions SET status='voided' "
                    "WHERE prescription_id=:id"
                ),
                {"id": draft["prescription_id"]},
            )
    elif case == "wrong_context":
        state["appointment"] = appointment.model_copy(update={"patient_id": uuid4()})
        expected = 404
    else:
        expected = 422
    response = client.post(
        issue_url(draft),
        **({"json": {"event_id": str(uuid4())}} if case == "tampered_body" else {}),
    )
    assert response.status_code == expected, response.text
    assert outbox_row(engine, draft["prescription_id"]) is None
    with Session(engine) as session:
        row = session.get(Prescription, UUID(draft["prescription_id"]))
        assert row.status == ("voided" if case == "voided" else "draft")
        assert row.issued_at is None


@pytest.mark.parametrize("failure", ["event_insert", "commit"])
def test_transaction_failure_restores_draft_and_no_event(api, failure):
    client, _, _, _, _, engine, app = api
    draft = create(api)

    def reject_event(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO clinical_records.event_outbox" in statement:
            raise OperationalError("unavailable", {}, Exception())

    def reject_commit(session):
        raise OperationalError("unavailable", {}, Exception())

    listener = reject_event if failure == "event_insert" else reject_commit
    hook = "before_cursor_execute" if failure == "event_insert" else "before_commit"
    target = app.state.database_engine if failure == "event_insert" else Session
    event.listen(target, hook, listener)
    try:
        assert client.post(issue_url(draft)).status_code == 503
    finally:
        event.remove(target, hook, listener)
    with Session(engine) as session:
        row = session.get(Prescription, UUID(draft["prescription_id"]))
        assert row.status == "draft" and row.issued_at is None
    assert outbox_row(engine, draft["prescription_id"]) is None
    assert client.post(issue_url(draft)).status_code == 200


def test_concurrent_issue_requests_return_same_resource(api):
    client, _, _, _, medication, engine, _ = api
    draft = create(api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(issue_url(draft)), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert outbox_row(engine, draft["prescription_id"]) is not None
    assert (
        client.patch(
            PREFIX + "/prescriptions/" + draft["prescription_id"], json=body(medication)
        ).status_code
        == 409
    )


def test_edit_racing_issue_cannot_modify_frozen_content(api):
    client, _, _, _, medication, engine, _ = api
    draft = create(api)
    replacement = body(medication)
    replacement["items"][0]["quantity"] = 3
    with ThreadPoolExecutor(max_workers=2) as pool:
        issuing = pool.submit(client.post, issue_url(draft))
        editing = pool.submit(
            client.patch, PREFIX + "/prescriptions/" + draft["prescription_id"], json=replacement
        )
        issued, edited = issuing.result(), editing.result()
    assert issued.status_code == 200
    assert edited.status_code in {200, 409}
    expected_quantity = 3 if edited.status_code == 200 else 2
    assert issued.json()["items"][0]["quantity"] == expected_quantity
    with Session(engine) as session:
        item = session.scalar(
            select(PrescriptionItem).where(
                PrescriptionItem.prescription_id == UUID(draft["prescription_id"])
            )
        )
        assert item.quantity == expected_quantity
    assert outbox_row(engine, draft["prescription_id"]) is not None


class EventBridge:
    def __init__(self, mode="success"):
        self.mode = mode
        self.entries = []

    def put_events(self, *, Entries):
        self.entries.extend(Entries)
        if self.mode == "timeout":
            raise TimeoutError("private provider message")
        return {
            "Entries": [
                {"EventId": str(uuid4())}
                if self.mode == "success"
                else {"ErrorCode": "ThrottlingException"}
                for _ in Entries
            ]
        }


@pytest.mark.parametrize("failure", ["timeout", "throttle"])
def test_shared_publisher_retries_same_committed_event(api, failure):
    client, _, _, _, _, engine, _ = api
    sessions = sessionmaker(engine)
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    # Drain earlier fixtures in this disposable database to isolate this event's retry.
    while publish_pending(sessions, event_outbox, EventBridge(), "test", now=now).published:
        pass
    draft = create(api)
    assert client.post(issue_url(draft)).status_code == 200
    stored = outbox_row(engine, draft["prescription_id"])
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    failing = EventBridge(failure)
    result = publish_pending(sessions, event_outbox, failing, "test", now=now)
    assert result.failed == 1 and result.published == 0
    failed = outbox_row(engine, draft["prescription_id"])
    assert failed.attempts == 1 and failed.published_at is None
    assert failed.last_error == ("TimeoutError" if failure == "timeout" else "ThrottlingException")
    assert failed.next_attempt_at > now
    assert publish_pending(sessions, event_outbox, EventBridge(), "test", now=now).published == 0
    successful = EventBridge()
    assert (
        publish_pending(
            sessions, event_outbox, successful, "test", now=failed.next_attempt_at
        ).published
        == 1
    )
    published = outbox_row(engine, draft["prescription_id"])
    assert published.published_at is not None
    assert published.event_id == stored.event_id and published.detail == stored.detail
    assert failing.entries[0]["Detail"] == successful.entries[0]["Detail"]
    assert (
        publish_pending(
            sessions, event_outbox, EventBridge(), "test", now=failed.next_attempt_at
        ).published
        == 0
    )
