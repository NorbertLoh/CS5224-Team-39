"""Synchronous SQLAlchemy sessions for sync FastAPI handlers and workers."""

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import ExampleItem
from app.settings import Settings


def create_database_engine(settings: Settings, **kwargs) -> Engine:
    if settings.database_url is None:
        raise ValueError("SERVICE_DATABASE_URL is required for database operations")
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.database_timeout_seconds,
            "options": f"-c statement_timeout={settings.database_timeout_seconds * 1000}",
        },
        hide_parameters=True,
        **kwargs,
    )


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_database_engine(settings)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def check_ready(self) -> None:
        # A connection alone is insufficient: verify the migration-created table exists.
        with self.engine.connect() as connection:
            connection.execute(select(ExampleItem.id).limit(1))

    def close(self) -> None:
        self.engine.dispose()


def get_session(request: Request) -> Iterator[Session]:
    database = request.app.state.database
    if database is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    # Closing rolls back any unfinished transaction. Writers explicitly use session.begin().
    with database.sessions() as session:
        yield session
