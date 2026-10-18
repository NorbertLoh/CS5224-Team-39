import os

from telelink_common.database import create_postgres_engine


def create_database_engine(url: str | None = None, **kwargs):
    return create_postgres_engine(url or os.environ.get("SERVICE_DATABASE_URL"), **kwargs)
