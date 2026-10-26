from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telelink_common.service_auth import service_token
from test_api import PREFIX
from test_api import api as api
from test_api import database as database

from app.models import MedicalCertificate, event_outbox

KEY = SecretStr("u17-consultation-records-secret-at-least-32-bytes")


def url(api):
    return PREFIX + f"/appointments/{api[3].appointment_id}/medical-certificate"


def draft(**changes):
    return {
        "selected": True,
        "start_date": "2026-10-31",
        "duration_days": 2,
        "additional_notes": "Rest & recover <safely>",
    } | changes


def completion(api):
    client, _, _, appointment, _, _, app = api
    app.state.settings.consultation_secret = KEY
    body = appointment.model_dump(mode="json", exclude={"status"}) | {
        "consultation_date": "2026-10-19",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = {
        "Authorization": "Bearer "
        + service_token(KEY, "consultation", "telelink-records-consultation")
    }
    return (
        client,
        PREFIX + f"/internal/appointments/{appointment.appointment_id}/complete-mc",
        body,
        headers,
    )


@pytest.mark.parametrize(
    "start,days,end",
    [
        ("2026-10-19", 1, "2026-10-19"),
        ("2026-10-31", 2, "2026-11-01"),
        ("2028-02-28", 3, "2028-03-01"),
    ],
)
def test_draft_roundtrip_and_inclusive_period(api, start, days, end):
    client = api[0]
    result = client.put(url(api), json=draft(start_date=start, duration_days=days))
    assert result.status_code == 200, result.text
    assert result.json()["end_date"] == end
    assert result.json()["issued_at"] is None
    assert client.get(url(api)).json() == result.json()
    api[1]["user"] = "patient"
    assert client.get(url(api)).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"duration_days": 0},
        {"duration_days": -1},
        {"duration_days": 1.5},
        {"duration_days": True},
        {"duration_days": "2"},
        {"duration_days": None},
        {"start_date": None},
        {"start_date": "2026-02-30"},
        {"start_date": "9999-12-31", "duration_days": 2},
        {"issued_at": "2026-10-19T00:00:00Z"},
        {"additional_notes": "x" * 20001},
    ],
)
def test_invalid_or_server_owned_fields_rejected(api, changes):
    assert api[0].put(url(api), json=draft(**changes)).status_code == 422


@pytest.mark.parametrize(
    "user", ["patient", "other_patient", "other_doctor", "cross_tenant", "admin", "platform"]
)
def test_only_current_assigned_doctor_can_save(api, user):
    api[1]["user"] = user
    assert api[0].put(url(api), json=draft()).status_code == 404


def test_completion_once_with_transactional_event_and_private_notes_excluded(api):
    assert api[0].put(url(api), json=draft()).status_code == 200
    client, path, body, headers = completion(api)
    assert client.post(path, json=body).status_code == 401
    results = list(
        ThreadPoolExecutor(4).map(lambda _: client.post(path, json=body, headers=headers), range(4))
    )
    assert all(result.status_code == 200 for result in results), [r.text for r in results]
    result = results[0].json()
    with Session(api[5]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(event_outbox)
                .where(event_outbox.c.detail.contains(str(api[3].tenant_id)))
            )
            == 1
        )
        row = session.get(MedicalCertificate, UUID(result["medical_certificate_id"]))
        assert row.issued_at is not None
    api[1]["appointment"].status = "completed"
    api[1]["user"] = "patient"
    assert client.get(url(api)).json()["issued_at"] == result["issued_at"]
    api[1]["user"] = "doctor"
    assert client.put(url(api), json=draft(duration_days=3)).status_code == 409
    assert (
        client.post(path, json=body | {"patient_id": str(uuid4())}, headers=headers).status_code
        == 404
    )


@pytest.mark.parametrize("save", [None, False])
def test_no_mc_completion_seals_decision_without_event(api, save):
    if save is False:
        assert api[0].put(url(api), json={"selected": False}).status_code == 200
    client, path, body, headers = completion(api)
    for _ in range(2):
        result = client.post(path, json=body, headers=headers)
        assert result.status_code == 200, result.text
        assert result.json()["issued_at"] is None and result.json()["finalized_at"]
    with Session(api[5]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(event_outbox)
                .where(event_outbox.c.detail.contains(str(api[3].tenant_id)))
            )
            == 0
        )
    # Even a stale scheduling response cannot reopen a sealed no-MC decision.
    assert client.put(url(api), json=draft()).status_code == 409


def test_finalization_and_event_roll_back_together(api):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    assert api[0].put(url(api), json=draft()).status_code == 200
    client, path, body, headers = completion(api)

    def fail_commit(session):
        if session.get_bind() is api[6].state.database_engine:
            raise OperationalError("synthetic commit failure", None, None)

    event.listen(Session, "before_commit", fail_commit)
    try:
        assert client.post(path, json=body, headers=headers).status_code == 503
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert client.get(url(api)).json()["finalized_at"] is None
    assert client.post(path, json=body, headers=headers).status_code == 200
    with Session(api[5]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(event_outbox)
                .where(event_outbox.c.detail.contains(str(api[3].tenant_id)))
            )
            == 1
        )


def test_mc_document_projection_is_service_only_and_excludes_private_notes(api, monkeypatch):
    from app.api import mc_documents
    from app.models import ServiceReadAudit

    assert api[0].put(url(api), json=draft()).status_code == 200
    client, path, body, headers = completion(api)
    mc = client.post(path, json=body, headers=headers).json()
    api[6].state.settings.document_secret = KEY

    def profile(client, base, path, secret, audience, request_id, model, params=None):
        return model.model_validate(
            {
                "patient_id": body["patient_id"],
                "patient_name": "Synthetic Patient",
                "doctor_id": body["doctor_id"],
                "doctor_name": "Synthetic Doctor",
            }
            if model is mc_documents.ParticipantNames
            else {"tenant_id": body["tenant_id"], "clinic_name": "Synthetic Clinic"}
        )

    monkeypatch.setattr(mc_documents, "profile", profile)
    document_path = (
        PREFIX + f"/internal/medical-certificates/{mc['medical_certificate_id']}/document"
    )
    params = {
        "tenant_id": body["tenant_id"],
        "appointment_id": body["appointment_id"],
        "purpose": "medical_certificate_pdf",
    }
    assert client.get(document_path, params=params).status_code == 401
    auth = {
        "Authorization": "Bearer " + service_token(KEY, "document", "telelink-records-document")
    }
    result = client.get(document_path, params=params, headers=auth)
    assert result.status_code == 200, result.text
    assert result.json()["additional_notes"] == draft()["additional_notes"]
    assert "text" not in result.json()
    assert (
        client.get(
            document_path, params=params | {"tenant_id": str(uuid4())}, headers=auth
        ).status_code
        == 404
    )
    with Session(api[5]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ServiceReadAudit)
                .where(
                    ServiceReadAudit.medical_certificate_id == UUID(mc["medical_certificate_id"])
                )
            )
            == 1
        )
