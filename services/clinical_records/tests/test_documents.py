from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import PREFIX, create
from test_api import api as api
from test_api import database as database

from app import documents
from app.models import ServiceReadAudit

KEY = SecretStr("document-records-test-key-at-least-32-bytes")


def projection(api, monkeypatch, *, issue=True):
    client, _, _, appointment, _, _, app = api
    app.state.settings.document_secret = KEY
    row = create(api)
    if issue:
        assert (
            client.post(PREFIX + f"/prescriptions/{row['prescription_id']}/issue").status_code
            == 200
        )

    def profile(client, base, path, secret, audience, request_id, model, params=None):
        return model.model_validate(
            {
                "patient_id": appointment.patient_id,
                "patient_name": "Synthetic Patient",
                "doctor_id": appointment.doctor_id,
                "doctor_name": "Synthetic Doctor",
            }
            if model is documents.ParticipantNames
            else {"tenant_id": appointment.tenant_id, "clinic_name": "Synthetic Clinic"}
        )

    monkeypatch.setattr(documents, "profile", profile)
    url = PREFIX + f"/internal/prescriptions/{row['prescription_id']}/document"
    params = {
        "tenant_id": str(appointment.tenant_id),
        "appointment_id": str(appointment.appointment_id),
        "purpose": "prescription_pdf",
    }
    auth = {
        "Authorization": "Bearer " + service_token(KEY, "document", "telelink-records-document")
    }
    return client, url, params, auth, row


def test_projection_is_service_only_context_bound_and_audited(api, monkeypatch):
    client, url, params, auth, row = projection(api, monkeypatch)
    assert (
        client.get(url, params=params).status_code == 401
    )  # Existing user-token override cannot grant service access.
    for field in ("tenant_id", "appointment_id"):
        assert (
            client.get(url, params=params | {field: str(uuid4())}, headers=auth).status_code == 404
        )
    assert client.get(url, params=params | {"purpose": "other"}, headers=auth).status_code == 422
    result = client.get(url, params=params, headers=auth)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["patient_name"] == "Synthetic Patient"
    assert "text" not in result.json() and "note" not in result.json()
    with Session(api[5]) as session:
        audit = session.scalar(
            select(ServiceReadAudit).where(
                ServiceReadAudit.prescription_id == UUID(row["prescription_id"])
            )
        )
        assert audit.caller == "document" and audit.purpose == "prescription_pdf"


def test_draft_cannot_be_fetched_for_generation(api, monkeypatch):
    client, url, params, auth, _ = projection(api, monkeypatch, issue=False)
    assert client.get(url, params=params, headers=auth).status_code == 409


def test_audit_failure_returns_no_clinical_response(api, monkeypatch):
    client, url, params, auth, row = projection(api, monkeypatch)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO clinical_records.service_read_audits" in statement:
            raise OperationalError(statement, {}, Exception("Synthetic audit outage"))

    event.listen(api[6].state.database_engine, "before_cursor_execute", fail)
    try:
        result = client.get(url, params=params, headers=auth)
        assert result.status_code == 503 and "Synthetic Patient" not in result.text
    finally:
        event.remove(api[6].state.database_engine, "before_cursor_execute", fail)
    with Session(api[5]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ServiceReadAudit)
                .where(ServiceReadAudit.prescription_id == UUID(row["prescription_id"]))
            )
            == 0
        )


@pytest.mark.parametrize("mode", ["valid", "down", "malformed", "timeout"])
def test_profile_adapter_validates_responses_without_leaking_input(mode):
    tenant = uuid4()

    def response(request):
        assert request.headers["authorization"].startswith("Bearer ey")
        if mode == "timeout":
            raise httpx.ReadTimeout("Synthetic private profile")
        return httpx.Response(
            503 if mode == "down" else 200,
            json={"tenant_id": str(tenant), "clinic_name": "Synthetic Clinic"}
            if mode != "malformed"
            else {"clinic_name": "Synthetic private profile"},
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        args = (
            client,
            "http://tenant",
            "/profile",
            KEY,
            "audience",
            "request",
            documents.ClinicName,
        )
        if mode == "valid":
            assert documents.profile(*args).tenant_id == tenant
        else:
            with pytest.raises(Exception) as error:
                documents.profile(*args)
            assert "Synthetic private profile" not in str(error.value)
