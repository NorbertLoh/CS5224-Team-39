"""Synchronous SQLAlchemy sessions for sync FastAPI handlers and workers."""

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from telelink_common.database import create_postgres_engine

from app.models import Order, Quote, event_inbox
from app.settings import Settings


def create_database_engine(settings: Settings, **kwargs) -> Engine:
    return create_postgres_engine(
        settings.database_url.get_secret_value() if settings.database_url is not None else None,
        timeout_seconds=settings.database_timeout_seconds,
        **kwargs,
    )


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_database_engine(settings)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def check_ready(self) -> None:
        # A connection alone is insufficient: verify the migration-created table exists.
        with self.engine.connect() as connection:
            connection.execute(select(Order.order_id).limit(1))
            connection.execute(select(Quote.quote_id).limit(1))
            connection.execute(select(event_inbox.c.event_id).limit(1))

    def close(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    database = request.app.state.database
    if database is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    # Closing rolls back any unfinished transaction. Writers explicitly use session.begin().
    with database.sessions() as session:
        yield session
