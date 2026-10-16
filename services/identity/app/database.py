"""PostgreSQL engine and explicit runtime subject resolution."""

import os
from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from telelink_common.database import create_postgres_engine

from app.models import Subject


def create_database_engine(url: str | None = None, **kwargs) -> Engine:
    return create_postgres_engine(url or os.environ.get("SERVICE_DATABASE_URL"), **kwargs)


def find_subject(session: Session, cognito_sub: str) -> Subject | None:
    """Caller must supply sub from a verified token; this performs no authentication."""
    return session.scalar(select(Subject).where(Subject.cognito_sub == cognito_sub))


def get_session(request: Request) -> Iterator[Session]:
    engine = request.app.state.database_engine
    if engine is None:
        raise HTTPException(503, "Identity storage is not configured")
    # Writers explicitly commit before returning; close rolls back unfinished reads/writes.
    with Session(engine, expire_on_commit=False) as session:
        yield session
