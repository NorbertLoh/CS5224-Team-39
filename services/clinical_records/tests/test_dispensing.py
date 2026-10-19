from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import PREFIX, create
from test_api import api as api
from test_api import database as database

from app.models import ServiceReadAudit

KEY = SecretStr("d07-records-fulfilment-test-secret-32-bytes")


def setup(api, issue=True):
    client, _, _, appointment, _, _, app = api
    app.state.settings.fulfilment_secret = KEY
    row = create(api)
    if issue:
        assert (
            client.post(PREFIX + f"/prescriptions/{row['prescription_id']}/issue").status_code
            == 200
        )
    path = PREFIX + f"/internal/prescriptions/{row['prescription_id']}/dispensing"
    params = {"patient_id": str(appointment.patient_id), "purpose": "dispensing"}
    headers = {
        "Authorization": "Bearer " + service_token(KEY, "fulfilment", "telelink-records-fulfilment")
    }
    return client, row, path, params, headers


def test_dispensing_is_minimal_context_bound_and_audited(api):
    client, row, path, params, headers = setup(api)
    assert client.get(path, params=params).status_code == 401
    assert (
        client.get(path, params=params | {"patient_id": str(uuid4())}, headers=headers).status_code
        == 404
    )
    assert (
        client.get(path, params=params | {"purpose": "other"}, headers=headers).status_code == 422
    )
    response = client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {
        "prescription_id",
        "appointment_id",
        "tenant_id",
        "patient_id",
        "status",
        "items",
    }
    assert set(result["items"][0]) == {"prescription_item_id", "medication_id", "quantity"}
    assert "instructions" not in response.text and "doctor_id" not in response.text
    with Session(api[5]) as session:
        audit = session.scalar(
            select(ServiceReadAudit).where(
                ServiceReadAudit.prescription_id == UUID(row["prescription_id"])
            )
        )
        assert audit.caller == "fulfilment" and audit.purpose == "dispensing"


def test_dispensing_draft_and_audit_outage_fail_closed(api):
    client, _, path, params, headers = setup(api, issue=False)
    assert client.get(path, params=params, headers=headers).status_code == 409
    # Issue the same prescription, then verify that audit failure exposes no projection.
    assert (
        client.post(path.replace("/internal", "").replace("/dispensing", "/issue")).status_code
        == 200
    )

    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO clinical_records.service_read_audits" in statement:
            raise OperationalError(statement, {}, Exception("Synthetic audit outage"))

    event.listen(api[6].state.database_engine, "before_cursor_execute", fail)
    try:
        response = client.get(path, params=params, headers=headers)
        assert response.status_code == 503 and "prescription_item_id" not in response.text
    finally:
        event.remove(api[6].state.database_engine, "before_cursor_execute", fail)
