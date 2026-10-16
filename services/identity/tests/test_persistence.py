import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine, find_subject
from app.models import Membership, Subject


def test_database_url_is_required_and_validated(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///identity.db", "postgresql+psycopg://host", "not a url"):
        with pytest.raises(ValueError):
            create_database_engine(url)


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    if os.environ.get("IDENTITY_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set IDENTITY_TEST_ALLOW_RESET=1: tests downgrade/delete identity data")
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
        assert inspect(engine).get_table_names(schema="identity") == ["alembic_version"]
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regprocedure('identity.touch_membership()')"))
                is None
            )
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


def create_subject(engine, **fields):
    fields.setdefault("cognito_sub", f"runtime-sub-{uuid4()}")
    fields.setdefault("display_name", "Synthetic doctor")
    with Session(engine) as session, session.begin():
        subject = Subject(**fields)
        session.add(subject)
        session.flush()
        return subject.subject_id, subject.cognito_sub


def test_runtime_mapping_roles_multiclinic_and_revocation(database):
    subject_id, sub = create_subject(database, global_roles=["patient", "platform_admin"])
    tenant_a, tenant_b = uuid4(), uuid4()
    with Session(database) as session, session.begin():
        a = Membership(subject_id=subject_id, tenant_id=tenant_a, roles=["doctor", "clinic_admin"])
        b = Membership(subject_id=subject_id, tenant_id=tenant_b, roles=["doctor"])
        session.add_all([a, b])
        session.flush()
        membership_id, created_at, updated_at = a.membership_id, a.created_at, a.updated_at
    with Session(database) as session, session.begin():
        subject = find_subject(session, sub)
        assert subject.subject_id == subject_id
        assert subject.global_roles == ["patient", "platform_admin"]
        assert find_subject(session, "synthetic-subject-4") is None
        assert find_subject(session, str(subject_id)) is None
        a = session.get(Membership, membership_id)
        a.status = "revoked"
        session.flush()
        assert a.updated_at > updated_at
        assert a.created_at == created_at
        assert a.updated_at.utcoffset().total_seconds() == 0
    with Session(database) as session, session.begin():
        memberships = session.scalars(
            select(Membership).where(Membership.subject_id == subject_id)
        ).all()
        assert len(memberships) == 2
        assert {m.status for m in memberships} == {"active", "revoked"}
        a = session.get(Membership, membership_id)
        a.roles = ["clinic_admin"]
        a.status = "active"
        # MutableList must persist in-place role changes too.
        subject = find_subject(session, sub)
        subject.global_roles.remove("platform_admin")
    with Session(database) as session:
        assert session.get(Membership, membership_id).roles == ["clinic_admin"]
        assert session.get(Membership, membership_id).created_at == created_at
        assert find_subject(session, sub).global_roles == ["patient"]


@pytest.mark.parametrize(
    "fields",
    [
        {"cognito_sub": ""},
        {"cognito_sub": "   "},
        {"display_name": ""},
        {"email": ""},
        {"email": "UPPER@example.test"},
        {"email": " padded@example.test "},
        {"global_roles": ["doctor"]},
        {"global_roles": ["clinic_admin"]},
        {"global_roles": ["patient", "patient"]},
        {"global_roles": [None]},
        {"global_roles": [["patient"]]},
    ],
)
def test_invalid_subject_fields_are_rejected(database, fields):
    with pytest.raises(IntegrityError):
        create_subject(database, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"roles": []},
        {"roles": ["patient"]},
        {"roles": ["platform_admin"]},
        {"roles": ["doctor", "doctor"]},
        {"roles": [None]},
        {"roles": [["doctor"]]},
        {"status": "pending"},
        {"subject_id": uuid4()},
    ],
)
def test_invalid_memberships_are_rejected(database, fields):
    subject_id, _ = create_subject(database)
    values = {"subject_id": subject_id, "tenant_id": uuid4(), "roles": ["doctor"]} | fields
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.add(Membership(**values))
        session.flush()


def test_unique_sub_membership_foreign_key_and_transaction_rollback(database):
    subject_id, sub = create_subject(database)
    with pytest.raises(IntegrityError):
        create_subject(database, cognito_sub=sub)
    tenant_id = uuid4()
    with Session(database) as session, session.begin():
        session.add(Membership(subject_id=subject_id, tenant_id=tenant_id, roles=["clinic_admin"]))
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.add(Membership(subject_id=subject_id, tenant_id=tenant_id, roles=["doctor"]))
        session.flush()
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.execute(delete(Subject).where(Subject.subject_id == subject_id))
    rolled_back_sub = f"rollback-{uuid4()}"
    with pytest.raises(RuntimeError), Session(database) as session, session.begin():
        session.add(Subject(cognito_sub=rolled_back_sub, display_name="Rollback"))
        session.flush()
        raise RuntimeError("intentional rollback")
    with Session(database) as session:
        assert find_subject(session, rolled_back_sub) is None


def test_email_is_unique_and_optional_for_legacy_subjects(database):
    email = f"unique-{uuid4()}@example.test"
    create_subject(database, email=email)
    with pytest.raises(IntegrityError):
        create_subject(database, email=email)
    create_subject(database, email=None)
    create_subject(database, email=None)


def test_operator_updates_refresh_timestamp_and_preserve_creation(database):
    subject_id, _ = create_subject(database)
    with Session(database) as session, session.begin():
        membership = Membership(subject_id=subject_id, tenant_id=uuid4(), roles=["doctor"])
        session.add(membership)
        session.flush()
        membership_id, created_at, updated_at = (
            membership.membership_id,
            membership.created_at,
            membership.updated_at,
        )
    with database.begin() as connection:
        row = connection.execute(
            text("""UPDATE identity.memberships SET status='revoked', created_at='2000-01-01'
                    WHERE membership_id=:id RETURNING created_at, updated_at"""),
            {"id": membership_id},
        ).one()
        assert row.created_at == created_at
        assert row.updated_at > updated_at


@pytest.mark.parametrize(
    "global_roles, roles",
    [
        ([], ["doctor"]),
        (["patient"], ["clinic_admin"]),
        (["platform_admin"], ["doctor", "clinic_admin"]),
        (["platform_admin", "patient"], ["clinic_admin", "doctor"]),
    ],
)
def test_valid_role_sets(database, global_roles, roles):
    subject_id, _ = create_subject(database, global_roles=global_roles)
    with Session(database) as session, session.begin():
        session.add(Membership(subject_id=subject_id, tenant_id=uuid4(), roles=roles))


@pytest.mark.parametrize(
    "table, column, value",
    [
        ("subjects", "cognito_sub", "NULL"),
        ("subjects", "global_roles", "NULL"),
        ("subjects", "global_roles", "'[0:0]={patient}'::text[]"),
        ("memberships", "roles", "NULL"),
        ("memberships", "status", "NULL"),
    ],
)
def test_raw_sql_cannot_bypass_required_fields(database, table, column, value):
    subject_id, _ = create_subject(database)
    with Session(database) as session, session.begin():
        session.add(Membership(subject_id=subject_id, tenant_id=uuid4(), roles=["doctor"]))
    # These identifiers/SQL literals are fixed test cases, never request input.
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            text(f"UPDATE identity.{table} SET {column}={value} WHERE subject_id=:id"),
            {"id": subject_id},
        )
