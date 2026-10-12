from alembic import context
from sqlalchemy import pool

from app.database import create_database_engine
from app.logging import configure_logging
from app.models import SERVICE_SCHEMA, Base
from app.settings import Settings

settings = Settings()
configure_logging(settings.log_level)
if settings.database_url is None:
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
}

if context.is_offline_mode():
    context.configure(
        url=settings.database_url.get_secret_value(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **options,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(settings, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **options)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
