import os

from alembic import context
from sqlalchemy import pool

from app.database import create_database_engine
from app.models import SERVICE_SCHEMA, Base

url = os.environ.get("SERVICE_DATABASE_URL")
if not url:
    raise ValueError("Set SERVICE_DATABASE_URL before running Alembic")


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SERVICE_SCHEMA
    return True


options = {
    "target_metadata": Base.metadata,
    "include_schemas": True,
    "include_name": include_name,
    "version_table_schema": SERVICE_SCHEMA,
    "compare_type": True,
    "compare_server_default": True,
}

if context.is_offline_mode():
    # Validate URL and dialect without opening a connection.
    engine = create_database_engine(url)
    try:
        context.configure(
            url=engine.url,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        engine.dispose()
else:
    engine = create_database_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **options)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
