import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import Document


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("DOCUMENT_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set DOCUMENT_TEST_ALLOW_RESET=1: tests downgrade/delete document data")
    previous = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        public_tables = inspect(engine).get_table_names(schema="public")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        yield engine
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="document") == ["alembic_version"]
        assert inspect(engine).get_table_names(schema="public") == public_tables
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regprocedure('document.touch_document()')"))
                is None
            )
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = previous


def values(kind="prescription_pdf", **overrides):
    source = {
        "prescription_pdf": "prescription_id",
        "receipt_pdf": "payment_id",
        "medical_certificate_pdf": "medical_certificate_id",
    }.get(kind, "prescription_id")
    return {
        "tenant_id": uuid4(),
        "appointment_id": uuid4(),
        "patient_id": uuid4(),
        "doctor_id": uuid4(),
        "kind": kind,
        source: uuid4(),
    } | overrides


def insert(engine, fields):
    with Session(engine) as session, session.begin():
        document = Document(**fields)
        session.add(document)
        session.flush()
        return document.document_id


@pytest.mark.parametrize("kind", ["prescription_pdf", "receipt_pdf", "medical_certificate_pdf"])
def test_metadata_and_source_deduplication(database, kind):
    fields = values(kind)
    document_id = insert(database, fields)
    with Session(database) as session:
        row = session.get(Document, document_id)
        assert row.status == "pending" and row.content_type == "application/pdf"
        assert row.created_at.utcoffset().total_seconds() == 0
    with pytest.raises(IntegrityError):
        insert(database, fields)
    # Tenant context is part of the generation key.
    insert(database, fields | {"tenant_id": uuid4()})


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "unknown"},
        {"status": "unknown"},
        {"patient_id": None},
        {"tenant_id": None},
        {"appointment_id": None},
        {"prescription_id": None},
        {"payment_id": uuid4()},
        {"doctor_id": None},
        {"content_type": "text/html"},
        {"status": "ready"},
        {"storage_key": "orphan.pdf"},
        {
            "status": "ready",
            "storage_bucket": "private",
            "storage_key": "key.pdf",
            "size_bytes": 1,
            "sha256": None,
        },
        {
            "status": "ready",
            "storage_bucket": "private",
            "storage_key": "key.pdf",
            "size_bytes": 0,
            "sha256": "a" * 64,
        },
    ],
)
def test_invalid_metadata_rejected(database, overrides):
    with pytest.raises(IntegrityError):
        insert(database, values(**overrides))


def test_ready_storage_and_database_timestamp_trigger(database):
    document_id = insert(database, values())
    with Session(database) as session, session.begin():
        row = session.get(Document, document_id)
        created = row.created_at
        updated = row.updated_at
        row.status = "ready"
        row.storage_bucket = "private-demo"
        row.storage_key = f"synthetic/{document_id}.pdf"
        row.size_bytes = 1024
        row.sha256 = "a" * 64
        session.flush()
        assert row.updated_at > updated
    with database.begin() as connection:
        row = connection.execute(
            text(
                "UPDATE document.documents SET created_at='2000-01-01' "
                "WHERE document_id=:id RETURNING created_at, updated_at"
            ),
            {"id": document_id},
        ).one()
        assert row.created_at == created
    with pytest.raises(IntegrityError):
        insert(
            database,
            values()
            | {
                "status": "ready",
                "storage_bucket": "private-demo",
                "storage_key": f"synthetic/{document_id}.pdf",
                "size_bytes": 1024,
                "sha256": "a" * 64,
            },
        )


def test_service_role_isolation(database):
    with database.connect() as connection:
        assert connection.scalar(text("SELECT current_user")) == "document"
        assert not connection.scalar(
            text("SELECT has_schema_privilege(current_user, 'p01_sentinel', 'CREATE')")
        )
        assert connection.scalar(text("SELECT marker FROM public.p01_sentinel")) == "untouched"


def test_database_url_validation(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///document.db", "postgresql+psycopg://host", "not a url"):
        with pytest.raises(ValueError):
            create_database_engine(url)
