import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.database import create_database_engine
from app.settings import Settings


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("FULFILMENT_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set FULFILMENT_TEST_ALLOW_RESET=1: tests delete fulfilment test data")
    original = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(Settings(database_url=url, environment="test"))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    yield engine
    engine.dispose()
    if original is None:
        os.environ.pop("SERVICE_DATABASE_URL", None)
    else:
        os.environ["SERVICE_DATABASE_URL"] = original


@pytest.fixture
def sessions(database):
    with database.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE fulfilment.deliveries, fulfilment.event_outbox, "
                "fulfilment.event_inbox, fulfilment.quote_requests, fulfilment.quotes, "
                "fulfilment.order_requests, fulfilment.order_items, "
                "fulfilment.orders, fulfilment.catalogue_items, fulfilment.prescription_prices"
            )
        )
    return sessionmaker(database, expire_on_commit=False)
