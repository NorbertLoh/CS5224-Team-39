"""Run against an explicitly disposable database using the service's restricted role."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import Note, Prescription, PrescriptionItem


def test_database_url_is_required_and_validated(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///records.db", "postgresql+psycopg://host", "not a url"):
        with pytest.raises(ValueError):
            create_database_engine(url)


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    if os.environ.get("CLINICAL_RECORDS_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set CLINICAL_RECORDS_TEST_ALLOW_RESET=1: tests downgrade clinical data")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        yield engine
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="clinical_records") == ["alembic_version"]
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regprocedure('clinical_records.touch_record()')"))
                is None
            )
            assert connection.scalar(text("SELECT value FROM unrelated.sentinel")) == "preserve"
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


def context():
    return {field: uuid4() for field in ("tenant_id", "appointment_id", "patient_id", "doctor_id")}


def insert(engine, model, **fields):
    with Session(engine) as session, session.begin():
        record = model(**fields)
        session.add(record)
        session.flush()
        return getattr(record, list(model.__table__.primary_key)[0].name)


def test_note_roundtrip_timestamp_and_external_context(database):
    fields = context()
    note_id = insert(database, Note, text="Synthetic note", **fields)
    with Session(database) as session, session.begin():
        note = session.get(Note, note_id)
        assert {key: getattr(note, key) for key in fields} == fields
        original_created, original_updated = note.created_at, note.updated_at
        assert original_created.utcoffset().total_seconds() == 0
        note.text = "Updated synthetic note"
        note.created_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        session.flush()
        session.refresh(note)
        assert note.created_at == original_created
        assert note.updated_at > original_updated


def test_one_note_per_appointment_even_with_different_tenant(database):
    fields = context()
    insert(database, Note, text="Synthetic", **fields)
    with pytest.raises(IntegrityError):
        insert(database, Note, text="Duplicate", **{**fields, "tenant_id": uuid4()})


@pytest.mark.parametrize("value", ["", "   ", None])
def test_empty_note_rejected(database, value):
    with pytest.raises(IntegrityError):
        insert(database, Note, text=value, **context())


@pytest.mark.parametrize("model", [Note, Prescription])
@pytest.mark.parametrize("field", ["tenant_id", "appointment_id", "patient_id", "doctor_id"])
def test_context_required(database, model, field):
    fields = {**context(), field: None}
    if model is Note:
        fields["text"] = "Synthetic"
    with pytest.raises(IntegrityError):
        insert(database, model, **fields)


def test_draft_issue_and_voided_replacement(database):
    fields = context()
    prescription_id = insert(database, Prescription, **fields)
    with pytest.raises(IntegrityError):
        insert(database, Prescription, **fields)
    with Session(database) as session, session.begin():
        prescription = session.get(Prescription, prescription_id)
        assert prescription.status == "draft"
        assert prescription.issued_at is None
        prescription.status = "issued"
        prescription.issued_at = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        insert(database, Prescription, **fields)
    with Session(database) as session, session.begin():
        session.get(Prescription, prescription_id).status = "voided"
    insert(database, Prescription, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "unknown"},
        {"status": "issued"},
        {"status": "draft", "issued_at": datetime.now(timezone.utc)},
        {"status": "issued", "issued_at": datetime.now(timezone.utc) - timedelta(days=1)},
    ],
)
def test_invalid_prescription_state_rejected(database, fields):
    with pytest.raises(IntegrityError):
        insert(database, Prescription, **context(), **fields)


def item_fields(prescription_id):
    return dict(
        prescription_id=prescription_id,
        medication_id=uuid4(),
        quantity=2,
        instructions="Synthetic instructions",
        display_name="Demo catalogue item",
    )


def test_item_roundtrip_and_parent_delete_restricted(database):
    parent_id = insert(database, Prescription, **context())
    fields = item_fields(parent_id)
    item_id = insert(database, PrescriptionItem, **fields)
    with Session(database) as session:
        item = session.get(PrescriptionItem, item_id)
        assert {key: getattr(item, key) for key in fields} == fields
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.delete(session.get(Prescription, parent_id))


@pytest.mark.parametrize(
    "fields",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": None},
        {"instructions": ""},
        {"instructions": "   "},
        {"instructions": None},
        {"display_name": ""},
        {"display_name": "   "},
        {"display_name": None},
        {"medication_id": None},
        {"prescription_id": uuid4()},
    ],
)
def test_invalid_items_rejected(database, fields):
    parent_id = insert(database, Prescription, **context())
    with pytest.raises(IntegrityError):
        insert(database, PrescriptionItem, **{**item_fields(parent_id), **fields})


def test_no_cross_service_foreign_keys_and_restricted_role(database):
    inspector = inspect(database)
    for table in ("notes", "prescriptions", "prescription_items"):
        for fk in inspector.get_foreign_keys(table, schema="clinical_records"):
            assert fk["referred_schema"] == "clinical_records"
    with database.connect() as connection:
        assert not connection.scalar(
            text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
        )
        assert connection.scalar(text("SELECT value FROM unrelated.sentinel")) == "preserve"
    with pytest.raises(ProgrammingError), database.begin() as connection:
        connection.execute(text("UPDATE unrelated.sentinel SET value='changed'"))
