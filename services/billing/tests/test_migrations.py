import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from telelink_common.database import create_postgres_engine

from tests.conftest import migrate


def test_fresh_upgrade_creates_billing_table(database_url):
    result = migrate(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_postgres_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "billing"
            assert connection.scalar(text("SHOW timezone")) == "UTC"
            assert (
                connection.scalar(text("SELECT version_num FROM billing.alembic_version")) == "0005"
            )
        assert set(inspect(engine).get_table_names(schema="billing")) == {
            "payments",
            "checkout_attempts",
            "checkout_keys",
            "medication_checkout_attempts",
            "medication_checkout_keys",
            "stripe_webhook_events",
            "event_outbox",
            "alembic_version",
        }
    finally:
        engine.dispose()


def test_migration_roundtrip_preserves_other_schemas(database, database_url):
    public_before = inspect(database).get_table_names(schema="public")
    for arguments in (("upgrade", "head"), ("check",), ("downgrade", "base")):
        result = migrate(database_url, *arguments)
        assert result.returncode == 0, result.stdout + result.stderr
    assert inspect(database).get_table_names(schema="billing") == ["alembic_version"]
    with database.connect() as connection:
        assert (
            connection.scalar(text("SELECT to_regprocedure('billing.protect_payment()')")) is None
        )
        assert connection.scalar(text("SELECT marker FROM b01_sentinel.records")) == "untouched"
        assert connection.scalar(text("SELECT marker FROM public.b01_sentinel")) == "untouched"
    assert inspect(database).get_table_names(schema="public") == public_before
    for arguments in (("upgrade", "head"), ("check",)):
        result = migrate(database_url, *arguments)
        assert result.returncode == 0, result.stdout + result.stderr


def test_billing_role_cannot_modify_other_schema(database):
    with pytest.raises(DBAPIError):
        with database.begin() as connection:
            connection.execute(text("UPDATE b01_sentinel.records SET marker='changed'"))
    with pytest.raises(DBAPIError):
        with database.begin() as connection:
            connection.execute(text("CREATE TABLE b01_sentinel.forbidden (id integer)"))
    with database.connect() as connection:
        assert not connection.scalar(
            text(
                "SELECT rolsuper OR rolcreaterole OR rolcreatedb "
                "FROM pg_roles WHERE rolname=current_user"
            )
        )


def test_database_url_rejects_other_dialects(monkeypatch):
    from app.database import create_database_engine

    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///billing.db", "not-a-url", "postgresql+psycopg://host"):
        with pytest.raises(ValueError):
            create_database_engine(url)
