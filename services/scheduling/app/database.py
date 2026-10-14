import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from telelink_common.database import create_postgres_engine
from telelink_common.errors import DomainError


def create_database_engine(url: str | None = None, **kwargs) -> Engine:
    return create_postgres_engine(url or os.environ.get("SERVICE_DATABASE_URL"), **kwargs)


def get_session(request: Request) -> Iterator[Session]:
    engine = request.app.state.database_engine
    if engine is None:
        raise DomainError(503, "unavailable", "Scheduling storage is not configured.")
    with Session(engine, expire_on_commit=False) as session:
        yield session
