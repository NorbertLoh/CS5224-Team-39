"""PostgreSQL-backed authorization/audit checks with explicit upstream/S3 adapters."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from telelink_common.access import CurrentIdentity, require_identity

from app.access import Appointment, AppointmentClient
from app.database import create_database_engine
from app.main import create_app
from app.models import AccessAudit, Document
from app.settings import Settings

PREFIX = "/api/v1/document/documents"


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("DOCUMENT_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set DOCUMENT_TEST_ALLOW_RESET=1 for disposable database tests")
    previous = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    try:
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        yield engine
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = previous


def identity(subject, tenant, role, status="active"):
    now = datetime.now(timezone.utc)
    return CurrentIdentity(
        subject_id=subject,
        cognito_sub=str(subject),
        display_name="Synthetic",
        global_roles=[role] if role in {"patient", "platform_admin"} else [],
        memberships=[]
        if role in {"patient", "platform_admin"}
        else [
            {
                "membership_id": uuid4(),
                "subject_id": subject,
                "tenant_id": tenant,
                "roles": [role],
                "status": status,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


@pytest.fixture
def api(database, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    tenant, patient, doctor, appointment_id = [uuid4() for _ in range(4)]
    appointment = Appointment(
        tenant_id=tenant, patient_id=patient, doctor_id=doctor, appointment_id=appointment_id
    )
    users = {
        "patient": identity(patient, tenant, "patient"),
        "doctor": identity(doctor, tenant, "doctor"),
        "other_patient": identity(uuid4(), tenant, "patient"),
        "other_doctor": identity(uuid4(), tenant, "doctor"),
        "cross_tenant": identity(doctor, uuid4(), "doctor"),
        "revoked": identity(doctor, tenant, "doctor", "revoked"),
        "admin": identity(uuid4(), tenant, "clinic_admin"),
        "platform": identity(uuid4(), tenant, "platform_admin"),
    }
    state = {"user": "patient", "appointment": appointment, "upstream_status": 200}
    settings = Settings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        scheduling_url="http://scheduling",
        cursor_secret="synthetic-cursor-key-at-least-32-bytes",
        aws_endpoint_url="http://floci:4566",
        s3_browser_endpoint_url="http://localhost:4566",
    )
    app = create_app(settings)
    app.dependency_overrides[require_identity] = lambda: users[state["user"]]
    with Session(database, expire_on_commit=False) as session:
        row = Document(
            **appointment.model_dump(),
            prescription_id=uuid4(),
            kind="prescription_pdf",
            status="ready",
            storage_bucket=settings.document_bucket,
            storage_key=f"synthetic/{uuid4()}.pdf",
            size_bytes=12,
            sha256="a" * 64,
        )
        session.add(row)
        session.commit()
    storage = Mock()
    storage.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            k: True
            for k in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        }
    }
    storage.head_object.return_value = {
        "ContentType": "application/pdf",
        "ContentLength": 12,
        "Metadata": {
            "sha256": row.sha256,
            "document-id": str(row.document_id),
            "tenant-id": str(tenant),
            "appointment-id": str(appointment_id),
            "patient-id": str(patient),
            "doctor-id": str(doctor),
        },
    }

    def upstream(request):
        assert request.headers["authorization"] == "Bearer synthetic"
        assert request.headers["x-request-id"]
        data = state["appointment"].model_dump(mode="json")
        if not state.get("wrong_id"):
            data["appointment_id"] = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(state["upstream_status"], json=data)

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.appointments.close()
        app.state.appointments = AppointmentClient(
            settings, transport=httpx.MockTransport(upstream)
        )
        app.state.downloads.storage = storage
        signer = app.state.downloads.signer
        original = signer.generate_presigned_url
        signer.generate_presigned_url = Mock(side_effect=original)
        client.headers.update({"Authorization": "Bearer synthetic"})
        yield client, state, row, database, app, storage, users


def download(api):
    client, _, row, *_ = api
    return client.get(f"{PREFIX}/{row.document_id}/download")


@pytest.mark.parametrize("user", ["patient", "doctor"])
def test_own_list_download_and_durable_audit(api, user):
    client, state, row, database, app, _, users = api
    state["user"] = user
    response = client.get(PREFIX, params={"appointment_id": str(row.appointment_id)})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["document_id"] == str(row.document_id)
    assert not {"storage_key", "storage_bucket", "sha256", "patient_id"} & item.keys()
    response = download(api)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    from urllib.parse import parse_qs, urlsplit

    url = urlsplit(response.json()["download_url"])
    assert url.hostname == "localhost"
    query = parse_qs(url.query)
    assert query["X-Amz-Expires"] == ["120"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["response-content-type"] == ["application/pdf"]
    assert "attachment" in query["response-content-disposition"][0]
    expires = datetime.fromisoformat(response.json()["expires_at"].replace("Z", "+00:00"))
    assert 110 < (expires - datetime.now(timezone.utc)).total_seconds() <= 120
    with Session(database) as session:
        audits = session.scalars(
            select(AccessAudit).where(AccessAudit.actor_id == users[user].subject_id)
        ).all()
        assert {a.action for a in audits} == {"list", "read", "download"}
        assert all(a.request_id for a in audits)
    assert app.state.downloads.signer.generate_presigned_url.call_count == 1


@pytest.mark.parametrize(
    "user", ["other_patient", "other_doctor", "cross_tenant", "revoked", "admin", "platform"]
)
def test_unrelated_roles_concealed_before_storage_or_signing(api, user):
    client, state, row, _, app, storage, _ = api
    state["user"] = user
    assert client.get(PREFIX).json()["items"] == []
    assert client.get(PREFIX, params={"appointment_id": str(row.appointment_id)}).status_code == 404
    assert download(api).status_code == 404
    storage.head_object.assert_not_called()
    app.state.downloads.signer.generate_presigned_url.assert_not_called()


@pytest.mark.parametrize("field", ["tenant_id", "patient_id", "doctor_id"])
def test_current_appointment_context_must_match_metadata(api, field):
    client, state, _, _, app, storage, _ = api
    state["appointment"] = state["appointment"].model_copy(update={field: uuid4()})
    assert client.get(PREFIX).status_code == 404
    assert download(api).status_code == 404
    storage.head_object.assert_not_called()
    app.state.downloads.signer.generate_presigned_url.assert_not_called()


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_not_ready(api, status):
    _, _, row, database, app, storage, _ = api
    with Session(database) as session, session.begin():
        current = session.get(Document, row.document_id)
        current.status = status
        current.storage_bucket = current.storage_key = current.sha256 = current.size_bytes = None
    assert download(api).status_code == 409
    storage.head_object.assert_not_called()
    app.state.downloads.signer.generate_presigned_url.assert_not_called()


@pytest.mark.parametrize(
    "status,expected", [(401, 401), (403, 404), (404, 404), (500, 503), (302, 502)]
)
def test_scheduling_failure_closed(api, status, expected):
    _, state, _, _, app, storage, _ = api
    state["upstream_status"] = status
    assert download(api).status_code == expected
    storage.head_object.assert_not_called()
    app.state.downloads.signer.generate_presigned_url.assert_not_called()


@pytest.mark.parametrize("operation", ["list", "download"])
def test_audit_failure_releases_no_data_or_url(api, operation):
    client, _, _, database, app, *_ = api

    def fail_audit(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO document.access_audits"):
            raise OperationalError("audit unavailable", {}, Exception("synthetic failure"))

    event.listen(database, "before_cursor_execute", fail_audit)
    # The app owns a separate engine; intercept that pool too.
    engine = app.state.database_engine
    event.listen(engine, "before_cursor_execute", fail_audit)
    try:
        response = client.get(PREFIX) if operation == "list" else download(api)
        assert response.status_code == 503
        assert "download_url" not in response.text and "storage_key" not in response.text
        app.state.downloads.signer.generate_presigned_url.assert_not_called()
    finally:
        event.remove(database, "before_cursor_execute", fail_audit)
        event.remove(engine, "before_cursor_execute", fail_audit)


def test_pagination_scoped_tamper_proof_and_stable(api):
    client, state, row, database, _, _, _ = api
    with Session(database) as session, session.begin():
        session.add_all(
            [
                Document(
                    tenant_id=row.tenant_id,
                    appointment_id=row.appointment_id,
                    patient_id=row.patient_id,
                    doctor_id=row.doctor_id,
                    prescription_id=uuid4(),
                    kind="prescription_pdf",
                    created_at=row.created_at + timedelta(days=1) if index == 0 else row.created_at,
                )
                for index in range(4)
            ]
        )
    ids, cursor, ordering = [], None, []
    while True:
        response = client.get(PREFIX, params={"limit": 1, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200
        data = response.json()
        ids.extend(item["document_id"] for item in data["items"])
        ordering.extend((item["created_at"], item["document_id"]) for item in data["items"])
        cursor = data["next_cursor"]
        if cursor is None:
            break
        assert client.get(PREFIX, params={"cursor": cursor + "x"}).status_code == 422
        assert (
            client.get(
                PREFIX, params={"cursor": cursor, "appointment_id": str(row.appointment_id)}
            ).status_code
            == 422
        )
        state["user"] = "doctor"
        assert client.get(PREFIX, params={"cursor": cursor}).status_code == 422
        state["user"] = "patient"
    assert len(ids) == len(set(ids)) == 5
    assert ordering == sorted(ordering, reverse=True)


def test_unauthenticated_and_missing_document(api):
    client, _, _, _, app, *_ = api
    app.dependency_overrides.clear()
    client.headers.pop("Authorization")
    assert client.get(PREFIX).status_code == 401
    assert download(api).status_code == 401


@pytest.mark.parametrize("failure", ["public", "integrity", "bucket", "missing"])
def test_storage_fails_closed(api, failure):
    _, _, row, database, app, storage, _ = api
    if failure == "public":
        storage.get_public_access_block.return_value = {"PublicAccessBlockConfiguration": {}}
    elif failure == "integrity":
        storage.head_object.return_value["Metadata"]["tenant-id"] = str(uuid4())
    elif failure == "bucket":
        with Session(database) as session, session.begin():
            session.get(Document, row.document_id).storage_bucket = "unexpected-bucket"
    else:
        from botocore.exceptions import ClientError

        storage.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "HeadObject"
        )
    assert download(api).status_code == 503
    app.state.downloads.signer.generate_presigned_url.assert_not_called()
