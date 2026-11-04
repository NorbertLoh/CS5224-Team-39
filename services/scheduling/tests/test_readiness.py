import os
from pathlib import Path

import pytest
import test_api
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app

api = test_api.api
api_database = test_api.api_database


@pytest.fixture
def ready_api(api):
    if not os.environ.get("TEST_REDIS_URL"):
        pytest.skip("Set TEST_REDIS_URL for readiness checks")
    assert api[0].app.state.hold_cache.ready()
    return api


def test_current_migration_head_is_ready(ready_api):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    with ready_api[-1].connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM scheduling.alembic_version")) == head
    response = ready_api[0].get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "scheduling"}


@pytest.mark.parametrize("revision", ["0005", "0006", None])
def test_stale_or_missing_revision_is_not_ready(ready_api, revision):
    client, *_, engine = ready_api
    assert client.get("/health/ready").status_code == 200
    with engine.connect() as connection:
        original = connection.scalar(text("SELECT version_num FROM scheduling.alembic_version"))
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM scheduling.alembic_version"))
            if revision is not None:
                connection.execute(
                    text("INSERT INTO scheduling.alembic_version VALUES (:revision)"),
                    {"revision": revision},
                )
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "service": "scheduling"}
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM scheduling.alembic_version"))
            connection.execute(
                text("INSERT INTO scheduling.alembic_version VALUES (:revision)"),
                {"revision": original},
            )


@pytest.mark.parametrize("dependency", ["database", "redis"])
def test_unavailable_dependency_is_not_ready(ready_api, dependency):
    settings = {
        "database_url": str(ready_api[-1].url.render_as_string(hide_password=False)),
        "redis_url": os.environ["TEST_REDIS_URL"],
    }
    if dependency == "database":
        settings["database_url"] = "postgresql+psycopg://unused:unused@127.0.0.1:1/unused"
        settings["database_timeout_seconds"] = 1
    else:
        settings["redis_url"] = "redis://127.0.0.1:1/0"
        settings["redis_timeout_seconds"] = 0.05
    with TestClient(create_app(test_api.configuration(**settings))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
