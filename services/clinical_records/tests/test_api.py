"""Real PostgreSQL + HTTP API checks, with explicit identity/appointment/catalogue adapters."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity

from app.database import create_database_engine
from app.main import create_app
from app.models import Note, Prescription, PrescriptionItem, ReadAudit
from app.settings import Settings
from app.upstream import Appointment, RecordsUpstream

PREFIX = "/api/v1/clinical-records"


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    if os.environ.get("CLINICAL_RECORDS_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set CLINICAL_RECORDS_TEST_ALLOW_RESET=1 for disposable database tests")
    previous = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    try:
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        engine = create_database_engine(url)
        yield engine
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = previous


def identity(subject_id, tenant_id, role):
    now = datetime.now(timezone.utc)
    return CurrentIdentity(
        subject_id=subject_id,
        cognito_sub=str(subject_id),
        display_name="Synthetic",
        global_roles=[role] if role in {"patient", "platform_admin"} else [],
        memberships=[]
        if role in {"patient", "platform_admin"}
        else [
            {
                "membership_id": uuid4(),
                "subject_id": subject_id,
                "tenant_id": tenant_id,
                "roles": [role],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


@pytest.fixture
def api(database):
    tenant, doctor, patient, medication, appointment_id = [uuid4() for _ in range(5)]
    appointment = Appointment(
        tenant_id=tenant,
        doctor_id=doctor,
        patient_id=patient,
        appointment_id=appointment_id,
        status="in_progress",
    )
    users = {
        "doctor": identity(doctor, tenant, "doctor"),
        "patient": identity(patient, tenant, "patient"),
        "other_patient": identity(uuid4(), tenant, "patient"),
        "other_doctor": identity(uuid4(), tenant, "doctor"),
        "cross_tenant": identity(doctor, uuid4(), "doctor"),
        "admin": identity(uuid4(), tenant, "clinic_admin"),
        "platform": identity(uuid4(), tenant, "platform_admin"),
    }
    state = {"appointment": appointment, "user": "doctor", "catalogue_status": 200}
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        scheduling_url="http://scheduling",
        fulfilment_url="http://fulfilment",
        cursor_secret="test-cursor-secret-at-least-32-bytes",
    )
    app = create_app(settings)
    app.dependency_overrides[require_identity] = lambda: users[state["user"]]

    def upstream(request):
        assert request.headers["authorization"] == "Bearer synthetic-token"
        assert request.headers["x-request-id"]
        if request.url.host == "scheduling":
            data = state["appointment"].model_dump(mode="json")
            # Extra generated appointments in the pagination test share trusted context.
            data["appointment_id"] = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(state.get("scheduling_status", 200), json=data)
        return httpx.Response(
            state["catalogue_status"],
            json={
                "items": [
                    {
                        "medication_id": str(medication),
                        "tenant_id": str(tenant),
                        "display_name": "Synthetic medicine",
                        "active": state.get("active", True),
                    }
                ],
                "next_cursor": None,
            },
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.upstream.close()
        app.state.upstream = RecordsUpstream(settings, transport=httpx.MockTransport(upstream))
        client.headers.update({"Authorization": "Bearer synthetic-token"})
        yield client, state, users, appointment, medication, database, app


def body(medication):
    return {
        "items": [
            {
                "medication_id": str(medication),
                "quantity": 2,
                "instructions": "Synthetic instructions",
            }
        ]
    }


def note_url(appointment):
    return PREFIX + f"/appointments/{appointment.appointment_id}/note"


def create(api):
    client, state, _, _, medication, _, _ = api
    appointment = state["appointment"]
    response = client.post(
        PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions", json=body(medication)
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_note_roundtrip_audit_and_no_store(api, caplog):
    client, state, _, appointment, _, engine, _ = api
    url = note_url(appointment)
    first = client.put(url, json={"text": "PRIVATE_SYNTHETIC_NOTE"})
    assert first.status_code == 201, first.text
    second = client.put(url, json={"text": "PRIVATE_SYNTHETIC_UPDATE"})
    assert second.status_code == 200
    assert second.json()["note_id"] == first.json()["note_id"]
    assert second.json()["created_at"] == first.json()["created_at"]
    state["user"] = "patient"
    result = client.get(url, headers={"X-Request-ID": "audit-test"})
    assert result.status_code == 200, result.text
    assert result.json()["text"] == "PRIVATE_SYNTHETIC_UPDATE"
    assert result.headers["cache-control"] == "no-store"
    with Session(engine) as session:
        audit = session.scalar(select(ReadAudit).where(ReadAudit.request_id == "audit-test"))
        assert audit.actor_id == appointment.patient_id
        assert audit.appointment_id == appointment.appointment_id
        assert audit.resource_id == UUID(first.json()["note_id"])
    assert "PRIVATE_SYNTHETIC" not in caplog.text


@pytest.mark.parametrize(
    "user", ["other_patient", "other_doctor", "cross_tenant", "admin", "platform"]
)
def test_unrelated_and_admin_access_concealed(api, user):
    client, state, _, appointment, medication, _, _ = api
    assert client.put(note_url(appointment), json={"text": "secret"}).status_code == 201
    prescription = create(api)
    state["user"] = user
    assert client.get(note_url(appointment)).status_code == 404
    assert client.put(note_url(appointment), json={"text": "tampered"}).status_code == 404
    detail = PREFIX + "/prescriptions/" + prescription["prescription_id"]
    assert client.get(detail).status_code == 404
    assert client.patch(detail, json=body(medication)).status_code == 404
    assert (
        client.get(
            PREFIX + "/prescriptions", params={"appointment_id": str(appointment.appointment_id)}
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "status",
    ["held", "pending_payment", "confirmed", "completed", "expired", "cancelled", "no_show"],
)
def test_write_requires_in_progress(api, status):
    client, state, _, appointment, medication, _, _ = api
    state["appointment"] = appointment.model_copy(update={"status": status})
    assert client.put(note_url(appointment), json={"text": "text"}).status_code == 409
    response = client.post(
        PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions", json=body(medication)
    )
    assert response.status_code == 409


def test_patient_read_after_completion_and_revoked_doctor(api):
    client, state, users, appointment, _, _, _ = api
    assert client.put(note_url(appointment), json={"text": "secret"}).status_code == 201
    state["appointment"] = appointment.model_copy(update={"status": "completed"})
    state["user"] = "patient"
    assert client.get(note_url(appointment)).status_code == 200
    assert client.put(note_url(appointment), json={"text": "tamper"}).status_code == 404
    state["user"] = "doctor"
    users["doctor"].memberships[0].__dict__["status"] = "revoked"
    assert client.get(note_url(appointment)).status_code == 404


def test_context_mismatch_and_missing_note_concealed(api):
    client, state, _, appointment, _, _, _ = api
    assert client.get(note_url(appointment)).status_code == 404
    client.put(note_url(appointment), json={"text": "secret"})
    state["appointment"] = appointment.model_copy(update={"tenant_id": uuid4()})
    state["user"] = "patient"
    assert client.get(note_url(appointment)).status_code == 404


def test_draft_lifecycle_server_links_and_issued_immutability(api):
    client, state, _, appointment, medication, engine, _ = api
    row = create(api)
    assert row["doctor_id"] == str(appointment.doctor_id)
    assert row["patient_id"] == str(appointment.patient_id)
    assert row["status"] == "draft" and row["issued_at"] is None
    assert row["items"][0]["display_name"] == "Synthetic medicine"
    url = PREFIX + "/prescriptions/" + row["prescription_id"]
    replacement = body(medication)
    replacement["items"][0]["quantity"] = 3
    updated = client.patch(url, json=replacement)
    assert updated.status_code == 200, updated.text
    assert updated.json()["items"][0]["quantity"] == 3
    assert updated.json()["updated_at"] >= row["updated_at"]
    assert (
        client.post(
            PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions",
            json=body(medication),
        ).status_code
        == 409
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE clinical_records.prescriptions SET status='issued', "
                "issued_at=clock_timestamp() WHERE prescription_id=:id"
            ),
            {"id": row["prescription_id"]},
        )
    assert client.patch(url, json=replacement).status_code == 409
    state["user"] = "patient"
    assert client.get(url).status_code == 200
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReadAudit)
                .where(ReadAudit.resource_id == UUID(row["prescription_id"]))
            )
            == 1
        )


@pytest.mark.parametrize("change", ["zero", "bool", "empty", "duplicate", "extra", "unknown"])
def test_item_validation(api, change):
    client, _, _, appointment, medication, _, _ = api
    data = body(medication)
    expected = 422
    if change == "zero":
        data["items"][0]["quantity"] = 0
    elif change == "bool":
        data["items"][0]["quantity"] = True
    elif change == "empty":
        data["items"] = []
    elif change == "duplicate":
        data["items"] *= 2
    elif change == "extra":
        data["patient_id"] = str(uuid4())
    else:
        data["items"][0]["medication_id"] = str(uuid4())
        expected = 409
    response = client.post(
        PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions", json=data
    )
    assert response.status_code == expected, response.text


def test_upstream_failure_rolls_back_replacement(api):
    client, state, _, _, medication, engine, _ = api
    row = create(api)
    state["catalogue_status"] = 503
    response = client.patch(
        PREFIX + "/prescriptions/" + row["prescription_id"], json=body(medication)
    )
    assert response.status_code == 503
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PrescriptionItem)
                .where(PrescriptionItem.prescription_id == UUID(row["prescription_id"]))
            )
            == 1
        )


def test_inactive_catalogue_and_scheduling_failure(api):
    client, state, _, appointment, medication, _, _ = api
    state["active"] = False
    response = client.post(
        PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions", json=body(medication)
    )
    assert response.status_code == 409
    state["scheduling_status"] = 503
    assert client.put(note_url(appointment), json={"text": "text"}).status_code == 503


def test_pagination_scoped_and_audited(api):
    client, state, _, appointment, medication, engine, _ = api
    first = create(api)
    other = appointment.model_copy(update={"appointment_id": uuid4()})
    state["appointment"] = other
    second = create(api)
    state["user"] = "patient"
    page = client.get(PREFIX + "/prescriptions", params={"limit": 1})
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 1 and page.json()["next_cursor"]
    assert page.json()["items"][0]["prescription_id"] == second["prescription_id"]
    cursor = page.json()["next_cursor"]
    next_page = client.get(PREFIX + "/prescriptions", params={"limit": 1, "cursor": cursor})
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["prescription_id"] == first["prescription_id"]
    assert {
        page.json()["items"][0]["prescription_id"],
        next_page.json()["items"][0]["prescription_id"],
    } == {first["prescription_id"], second["prescription_id"]}
    assert next_page.json()["next_cursor"] is None
    assert (
        client.get(PREFIX + "/prescriptions", params={"cursor": cursor + "bad"}).status_code == 422
    )
    assert (
        client.get(
            PREFIX + "/prescriptions",
            params={"cursor": cursor, "appointment_id": str(other.appointment_id)},
        ).status_code
        == 422
    )
    state["user"] = "other_patient"
    assert client.get(PREFIX + "/prescriptions", params={"cursor": cursor}).status_code == 422
    assert client.get(PREFIX + "/prescriptions").json()["items"] == []
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReadAudit)
                .where(ReadAudit.resource_id == UUID(first["prescription_id"]))
            )
            == 1
        )


def test_audit_failure_never_returns_content(api):
    client, _, _, appointment, _, engine, _ = api
    client.put(note_url(appointment), json={"text": "must-not-leak"})

    def reject_audit(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO clinical_records.read_audits" in statement:
            raise OperationalError("audit unavailable", {}, Exception())

    event.listen(engine, "before_cursor_execute", reject_audit)
    # The application's pool is separate from the fixture pool.
    app_engine = api[-1].state.database_engine
    event.listen(app_engine, "before_cursor_execute", reject_audit)
    try:
        result = client.get(note_url(appointment))
        assert result.status_code == 503, result.text
        assert "must-not-leak" not in result.text
    finally:
        event.remove(engine, "before_cursor_execute", reject_audit)
        event.remove(app_engine, "before_cursor_execute", reject_audit)


def test_concurrent_first_writes_and_prescriptions(api):
    client, _, _, appointment, medication, engine, _ = api
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.put(note_url(appointment), json={"text": "concurrent"}).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 201]
    url = PREFIX + f"/appointments/{appointment.appointment_id}/prescriptions"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post(url, json=body(medication)).status_code, range(2))
        )
    assert sorted(results) == [201, 409]
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Note)
                .where(Note.appointment_id == appointment.appointment_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Prescription)
                .where(Prescription.appointment_id == appointment.appointment_id)
            )
            == 1
        )


def test_missing_bearer_and_unready_configuration():
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        response = client.get(PREFIX + f"/appointments/{uuid4()}/note")
        assert response.status_code == 401
        assert client.get("/health/ready").status_code == 503
