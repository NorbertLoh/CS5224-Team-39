from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_api import PREFIX, api, create, database

from app.models import ReadAudit

__all__ = ["api", "database"]


def historical(api, status="issued"):
    row = create(api)
    client, state, _, appointment, _, engine, _ = api
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE clinical_records.prescriptions SET status=:status, "
                "issued_at=clock_timestamp() WHERE prescription_id=:id"
            ),
            {"status": status, "id": row["prescription_id"]},
        )
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    state["user"] = "other_doctor"
    state["history_for"] = str(uuid4())
    return row, {
        "appointment_id": str(appointment.appointment_id),
        "history_for": state["history_for"],
    }


def test_other_doctor_reads_audited_history_without_ordinary_access(api):
    row, params = historical(api)
    client, state, users, _, _, engine, _ = api
    endpoint = PREFIX + "/prescriptions"
    assert (
        client.get(endpoint, params={"appointment_id": params["appointment_id"]}).status_code == 404
    )
    result = client.get(endpoint, params=params, headers={"X-Request-ID": "rf54-history"})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    saved = result.json()["items"][0]
    assert saved["prescription_id"] == row["prescription_id"]
    assert saved["items"][0]["display_name"] == "Synthetic medicine"
    assert saved["items"][0]["instructions"] == "Synthetic instructions"
    with Session(engine) as db:
        audits = db.scalars(select(ReadAudit).where(ReadAudit.request_id == "rf54-history")).all()
        assert {audit.resource_type for audit in audits} == {"prescription", "prescription_list"}
        assert all(audit.actor_id == users["other_doctor"].subject_id for audit in audits)
    assert (
        client.get(PREFIX + "/prescriptions/" + row["prescription_id"], params=params).status_code
        == 404
    )
    assert client.patch(
        PREFIX + "/prescriptions/" + row["prescription_id"], params=params, json={"items": []}
    ).status_code in {404, 422}
    state["scheduling_status"] = 404
    assert client.get(endpoint, params=params).status_code == 404


@pytest.mark.parametrize("role", ["patient", "other_patient", "admin", "platform", "cross_tenant"])
def test_history_rejects_non_clinic_doctors(api, role):
    _, params = historical(api)
    api[1]["user"] = role
    assert api[0].get(PREFIX + "/prescriptions", params=params).status_code == 404


def test_history_requires_completed_visit_and_explicit_appointment(api):
    _, params = historical(api)
    client, state, _, appointment, _, _, _ = api
    assert (
        client.get(
            PREFIX + "/prescriptions", params={"history_for": params["history_for"]}
        ).status_code
        == 422
    )
    state["appointment"] = appointment
    assert client.get(PREFIX + "/prescriptions", params=params).status_code == 404


def test_history_excludes_drafts_and_mismatched_record_context(api):
    row = create(api)
    client, state, _, appointment, _, _, _ = api
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    state["user"] = "other_doctor"
    state["history_for"] = str(uuid4())
    params = {
        "appointment_id": str(appointment.appointment_id),
        "history_for": state["history_for"],
    }
    assert client.get(PREFIX + "/prescriptions", params=params).json()["items"] == []
    with api[5].begin() as connection:
        connection.execute(
            text(
                "UPDATE clinical_records.prescriptions SET status='issued', "
                "issued_at=clock_timestamp() WHERE prescription_id=:id"
            ),
            {"id": row["prescription_id"]},
        )
    for field in ("patient_id", "tenant_id", "doctor_id"):
        state["appointment"] = appointment.model_copy(
            update={"status": "completed", field: uuid4()}
        )
        result = client.get(PREFIX + "/prescriptions", params=params)
        assert result.status_code == 404 or result.json()["items"] == []


def test_history_pagination_is_bound_to_anchor_and_keeps_voided_status(api):
    old, params = historical(api, "voided")
    client, state, _, appointment, _, engine, _ = api
    state["appointment"] = appointment
    state["user"] = "doctor"
    new = create(api)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE clinical_records.prescriptions SET status='issued', "
                "issued_at=clock_timestamp() WHERE prescription_id=:id"
            ),
            {"id": new["prescription_id"]},
        )
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    state["user"] = "other_doctor"
    first = client.get(PREFIX + "/prescriptions", params=params | {"limit": 1}).json()
    assert first["items"][0]["prescription_id"] == new["prescription_id"]
    cursor = first["next_cursor"]
    assert cursor
    second = client.get(PREFIX + "/prescriptions", params=params | {"cursor": cursor}).json()
    assert second["items"][0]["prescription_id"] == old["prescription_id"]
    assert second["items"][0]["status"] == "voided"
    assert second["next_cursor"] is None
    state["history_for"] = str(uuid4())
    changed = params | {"history_for": state["history_for"], "cursor": cursor}
    assert client.get(PREFIX + "/prescriptions", params=changed).status_code == 422
    state["user"] = "doctor"
    assert (
        client.get(
            PREFIX + "/prescriptions",
            params={"appointment_id": params["appointment_id"], "cursor": cursor},
        ).status_code
        == 422
    )


def test_history_audit_failure_does_not_return_prescriptions(api):
    row, params = historical(api)
    client, _, _, _, _, _, app = api

    def reject(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO clinical_records.read_audits" in statement:
            raise OperationalError("audit unavailable", {}, Exception())

    engine = app.state.database_engine
    event.listen(engine, "before_cursor_execute", reject)
    try:
        result = client.get(PREFIX + "/prescriptions", params=params)
        assert result.status_code == 503
        assert row["prescription_id"] not in result.text
    finally:
        event.remove(engine, "before_cursor_execute", reject)
