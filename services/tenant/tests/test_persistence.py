import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import Clinic


def test_database_url_validation(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///tenant.db", "postgresql+psycopg://host", "not a url"):
        with pytest.raises(ValueError):
            create_database_engine(url)


def clear_disposable_rows(engine):
    # API checks share this explicitly resettable database. Clear their fixtures
    # before testing downgrade; production audit/history guards remain enabled.
    tables = inspect(engine).get_table_names(schema="tenant")
    quote = engine.dialect.identifier_preparer.quote
    names = [f"tenant.{quote(name)}" for name in tables if name != "alembic_version"]
    if names:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE TABLE " + ", ".join(names)))


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("TENANT_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set TENANT_TEST_ALLOW_RESET=1: tests downgrade/delete tenant data")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        public_tables = inspect(engine).get_table_names(schema="public")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        clear_disposable_rows(engine)
        # A08 is additive: rolling back just 0002 preserves the A07 clinic rows.
        clinic_id = create_clinic(engine)
        command.downgrade(config, "0002")
        assert "audit_events" not in inspect(engine).get_table_names(schema="tenant")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT tenant_id FROM tenant.clinics WHERE tenant_id=:id"),
                    {"id": clinic_id},
                )
                == clinic_id
            )
            assert (
                connection.scalar(text("SELECT to_regprocedure('tenant.prevent_audit_mutation()')"))
                is None
            )
        command.downgrade(config, "0001")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT tenant_id FROM tenant.clinics WHERE tenant_id=:id"),
                    {"id": clinic_id},
                )
                == clinic_id
            )
        command.upgrade(config, "head")
        command.check(config)
        assert sorted(inspect(engine).get_table_names(schema="tenant")) == [
            "alembic_version",
            "audit_events",
            "clinic_locations",
            "clinics",
        ]
        yield engine
        clear_disposable_rows(engine)
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="tenant") == ["alembic_version"]
        assert inspect(engine).get_table_names(schema="public") == public_tables
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regprocedure('tenant.touch_clinic()')")) is None
            )
            assert (
                connection.scalar(text("SELECT to_regprocedure('tenant.prevent_audit_mutation()')"))
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


def create_clinic(engine, **fields):
    values = {
        "slug": f"synthetic-{uuid4()}",
        "name": "Synthetic clinic",
        "primary_color": "#156B63",
        "description": "Synthetic clinic for prototype walkthroughs.",
        "consultation_price_minor": 2500,
    } | fields
    with Session(engine) as session, session.begin():
        clinic = Clinic(**values)
        session.add(clinic)
        session.flush()
        return clinic.tenant_id


def test_defaults_branding_and_timestamps(database):
    tenant_id = create_clinic(database)
    assert isinstance(tenant_id, UUID)
    with Session(database) as session:
        clinic = session.get(Clinic, tenant_id)
        assert (clinic.status, clinic.commission_bps, clinic.currency) == (
            "pending_review",
            0,
            "SGD",
        )
        assert clinic.logo_url is None and clinic.review_reason is None
        created_at, updated_at = clinic.created_at, clinic.updated_at
        assert created_at.utcoffset().total_seconds() == 0
    with Session(database) as session, session.begin():
        clinic = session.get(Clinic, tenant_id)
        clinic.name = "Updated clinic"
        clinic.primary_color = "#aabbcc"
        clinic.logo_url = "https://example.com/logo.png"
        clinic.description = "Updated description"
        session.flush()
        assert clinic.updated_at > updated_at
        assert clinic.created_at == created_at
        updated_at = clinic.updated_at
    # Trigger also handles direct SQL and prevents rewriting creation time.
    with database.begin() as connection:
        row = connection.execute(
            text("""UPDATE tenant.clinics SET name='SQL update', created_at='2000-01-01'
                    WHERE tenant_id=:id RETURNING created_at, updated_at"""),
            {"id": tenant_id},
        ).one()
        assert row.created_at == created_at and row.updated_at > updated_at


@pytest.mark.parametrize(
    "fields",
    [
        {"slug": "   "},
        {"name": ""},
        {"status": "approved"},
        {"primary_color": "red"},
        {"primary_color": "#1234567"},
        {"logo_url": "http://example.com/logo.png"},
        {"logo_url": "https://"},
        {"logo_url": "https://example.com/a b"},
        {"consultation_price_minor": -1},
        {"consultation_price_minor": 9007199254740992},
        {"currency": "USD"},
        {"commission_bps": -1},
        {"commission_bps": 10001},
        {"review_reason": "   "},
    ],
)
def test_invalid_fields(database, fields):
    with pytest.raises(IntegrityError):
        create_clinic(database, **fields)


@pytest.mark.parametrize("status", ["pending_review", "active", "rejected", "suspended"])
def test_valid_states_and_price_boundaries(database, status):
    for price, commission in ((0, 0), (9007199254740991, 10000)):
        create_clinic(
            database,
            status=status,
            consultation_price_minor=price,
            commission_bps=commission,
            review_reason="Synthetic review" if status in {"rejected", "suspended"} else None,
        )


def test_unique_immutable_slug_and_rollback(database):
    slug = f"unique-{uuid4()}"
    tenant_id = create_clinic(database, slug=slug)
    with pytest.raises(IntegrityError):
        create_clinic(database, slug=slug)
    with pytest.raises(IntegrityError), Session(database) as session, session.begin():
        session.get(Clinic, tenant_id).slug = f"changed-{uuid4()}"
        session.flush()
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            text("UPDATE tenant.clinics SET slug='changed' WHERE tenant_id=:id"), {"id": tenant_id}
        )
    with Session(database) as session:
        assert session.get(Clinic, tenant_id).slug == slug
    rolled_back_id = uuid4()
    with pytest.raises(RuntimeError), Session(database) as session, session.begin():
        session.add(
            Clinic(
                tenant_id=rolled_back_id,
                slug=f"rollback-{uuid4()}",
                name="Rollback",
                primary_color="#123456",
                description="",
                consultation_price_minor=0,
            )
        )
        session.flush()
        raise RuntimeError("intentional rollback")
    with Session(database) as session:
        assert session.get(Clinic, rolled_back_id) is None


@pytest.mark.parametrize(
    "column",
    [
        "tenant_id",
        "slug",
        "name",
        "status",
        "primary_color",
        "description",
        "consultation_price_minor",
        "currency",
        "commission_bps",
        "membership_provisioned",
    ],
)
def test_required_fields_in_direct_sql(database, column):
    tenant_id = create_clinic(database)
    # Column identifiers are fixed test cases, never user input.
    with pytest.raises(IntegrityError), database.begin() as connection:
        connection.execute(
            text(f"UPDATE tenant.clinics SET {column}=NULL WHERE tenant_id=:id"), {"id": tenant_id}
        )
