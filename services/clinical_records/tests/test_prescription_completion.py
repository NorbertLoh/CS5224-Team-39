"""Completion issues existing drafts, including retries on old completed visits."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy.orm import Session
from test_api import PREFIX, body, create
from test_api import api as api
from test_api import database as database
from test_issuance import outbox_row

from app.models import Prescription


def completion_url(appointment):
    return PREFIX + f"/appointments/{appointment.appointment_id}/finalize-prescription"


@pytest.mark.parametrize("completed", [False, True])
def test_completion_issues_once_and_keeps_completed_drafts_immutable(api, completed):
    client, state, _, appointment, medication, engine, _ = api
    draft = create(api)
    if completed:
        state["appointment"] = appointment.model_copy(update={"status": "completed"})
    url = completion_url(appointment)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(url), range(2)))
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert results[0].json()["prescription_id"] == draft["prescription_id"]
    assert results[0].json()["status"] == "issued"
    event = outbox_row(engine, draft["prescription_id"])
    assert event is not None
    state["catalogue_status"] = 503
    assert client.post(url).json() == results[0].json()
    assert outbox_row(engine, draft["prescription_id"]).detail == event.detail
    assert (
        client.patch(
            PREFIX + "/prescriptions/" + draft["prescription_id"], json=body(medication)
        ).status_code
        == 409
    )


@pytest.mark.parametrize("completed", [False, True])
def test_completion_without_prescription_is_valid_and_creates_nothing(api, completed):
    client, state, _, appointment, _, _, _ = api
    if completed:
        state["appointment"] = appointment.model_copy(update={"status": "completed"})
    response = client.post(completion_url(appointment))
    assert response.status_code == 200
    assert response.json()["status"] == "none"
    assert response.json()["prescription_id"] is None


@pytest.mark.parametrize(
    "user",
    ["patient", "other_patient", "other_doctor", "cross_tenant", "admin", "platform", "revoked"],
)
def test_completion_requires_assigned_active_doctor(api, user):
    client, state, users, appointment, _, engine, _ = api
    draft = create(api)
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    if user == "revoked":
        users["doctor"].memberships[0].__dict__["status"] = "revoked"
    else:
        state["user"] = user
    assert client.post(completion_url(appointment)).status_code == 404
    assert outbox_row(engine, draft["prescription_id"]) is None


@pytest.mark.parametrize("status", ["confirmed", "cancelled", "expired", "no_show"])
def test_completion_rejects_unstarted_or_cancelled_visits(api, status):
    client, state, _, appointment, _, _, _ = api
    state["appointment"] = appointment.model_copy(update={"status": status})
    assert client.post(completion_url(appointment)).status_code == 409


def test_completion_failure_preserves_draft_and_stages_no_event(api):
    client, state, _, appointment, _, engine, _ = api
    draft = create(api)
    state["active"] = False
    assert client.post(completion_url(appointment)).status_code == 409
    assert outbox_row(engine, draft["prescription_id"]) is None
    with Session(engine) as session:
        assert session.get(Prescription, UUID(draft["prescription_id"])).status == "draft"
