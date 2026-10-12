import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import Database, get_session
from app.main import create_app
from app.models import ExampleItem
from app.settings import Settings


def test_database_configuration_is_optional_validated_and_redacted():
    assert Settings(_env_file=None).database_url is None
    settings = Settings(_env_file=None, database_url="postgresql+psycopg://u:secret@localhost/db")
    assert "secret" not in repr(settings)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///test.db")


def test_session_dependency_without_database_returns_503():
    app = create_app(Settings(_env_file=None))

    @app.get("/db-example")
    def example(session: Session = Depends(get_session)):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/db-example")
        assert response.status_code == 503
        assert response.json()["detail"] == "Database is not configured"


@pytest.fixture
def migrated_database(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database to run integration")
    # This fixture mutates only template.example_items through Alembic. No drop database/schema.
    monkeypatch.setenv("SERVICE_DATABASE_URL", url)
    database = Database(Settings(_env_file=None, database_url=url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    try:
        yield database, config
    finally:
        database.close()


def test_postgres_migrations_transactions_and_readiness(migrated_database):
    database, config = migrated_database
    command.check(config)
    with database.engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM template.alembic_version")) == "0001"
    name = f"test-{uuid4()}"
    with database.sessions.begin() as session:
        item = ExampleItem(name=name)
        session.add(item)
        session.flush()
        item_id = item.id
    with database.sessions() as session:
        stored = session.get(ExampleItem, item_id)
        assert stored.name == name
        assert stored.created_at.tzinfo is not None

    rolled_back_name = f"rollback-{uuid4()}"
    with pytest.raises(RuntimeError):
        with database.sessions.begin() as session:
            session.add(ExampleItem(name=rolled_back_name))
            session.flush()
            raise RuntimeError("intentional rollback")
    with database.sessions() as session:
        assert (
            session.scalar(select(ExampleItem).where(ExampleItem.name == rolled_back_name)) is None
        )

    app = create_app(Settings(_env_file=None, database_url=os.environ["TEST_DATABASE_URL"]))

    @app.get("/session-example")
    def session_example(session: Session = Depends(get_session)):
        return {"name": session.get(ExampleItem, item_id).name}

    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/session-example").json() == {"name": name}
        command.downgrade(config, "base")
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert "example_items" not in response.text
        command.upgrade(config, "head")
        assert client.get("/health/ready").status_code == 200
    assert app.state.database is None
    command.check(config)
