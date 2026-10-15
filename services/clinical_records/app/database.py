"""Use a service-owned PostgreSQL role/schema, never another service's tables."""

import os

from sqlalchemy.engine import Engine
from telelink_common.database import create_postgres_engine


def create_database_engine(url: str | None = None, **kwargs) -> Engine:
    return create_postgres_engine(url or os.environ.get("SERVICE_DATABASE_URL"), **kwargs)
