"""PostgreSQL engine and explicit runtime subject resolution."""

import os

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.models import Subject


def create_database_engine(url: str | None = None, **kwargs) -> Engine:
    value = url or os.environ.get("SERVICE_DATABASE_URL")
    if not value:
        raise ValueError("Set SERVICE_DATABASE_URL before identity database operations")
    try:
        parsed = make_url(value)
    except Exception:
        raise ValueError("SERVICE_DATABASE_URL must be a valid PostgreSQL URL") from None
    if parsed.drivername != "postgresql+psycopg" or not parsed.database:
        raise ValueError("SERVICE_DATABASE_URL requires postgresql+psycopg and a database name")
    return create_engine(
        parsed,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c search_path=public -c timezone=UTC -c statement_timeout=3000",
        },
        **kwargs,
    )


def find_subject(session: Session, cognito_sub: str) -> Subject | None:
    """Caller must supply sub from a verified token; this performs no authentication."""
    return session.scalar(select(Subject).where(Subject.cognito_sub == cognito_sub))
