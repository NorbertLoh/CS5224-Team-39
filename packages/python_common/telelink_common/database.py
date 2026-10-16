"""Engine construction only; sessions, readiness, models and migrations stay local."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def create_postgres_engine(url: str | None, *, timeout_seconds: int = 3, **kwargs) -> Engine:
    if not url:
        raise ValueError("SERVICE_DATABASE_URL is required for database operations")
    try:
        parsed = make_url(url)
    except Exception:
        raise ValueError("SERVICE_DATABASE_URL must be a valid PostgreSQL URL") from None
    if parsed.drivername != "postgresql+psycopg" or not parsed.database:
        raise ValueError("SERVICE_DATABASE_URL requires postgresql+psycopg and a database name")
    return create_engine(
        parsed,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": timeout_seconds,
            "options": (
                "-c search_path=public -c timezone=UTC "
                f"-c statement_timeout={timeout_seconds * 1000}"
            ),
        },
        **kwargs,
    )
