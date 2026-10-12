# SQLAlchemy and Alembic example

The template uses synchronous SQLAlchemy 2 sessions and psycopg 3 with PostgreSQL. `app/models.py` owns schema `template`; Alembic stores its revision in `template.alembic_version`. Models explicitly qualify their schema and connections use `search_path=public` so same-named roles/schemas do not confuse migration reflection. The schema is a service boundary, not one schema per clinic. Business tasks must add tenant IDs and access policies to their own models.

Database mode is optional. With `SERVICE_DATABASE_URL` unset, the F03 health-only server still runs. With it configured, `/health/ready` checks the migrated example table and returns 503 if the database/table is unavailable. `/health/live` remains independent of PostgreSQL. Startup never creates tables or runs migrations.

## Fresh local database (PowerShell)

Start Docker Desktop and use a dedicated local container. Commands below use disposable demonstration credentials and bind PostgreSQL to localhost. This is a standalone validation setup, not the future Compose configuration.

From `services/template`:

```powershell
docker run --name telelink-f04-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=f04-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55404:5432 -d postgres:17
docker exec telelink-f04-postgres pg_isready -U postgres -d telelink
```

Wait until `pg_isready` reports accepting connections. If that container already exists, use `docker start telelink-f04-postgres` rather than creating another. Choose another local port if 55404 is occupied and update the URL accordingly.

Provision the service-owned schema once, as administrator:

```powershell
Get-Content -Raw scripts/create-local-schema.sql | docker exec -i telelink-f04-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
```

The script intentionally targets a fresh database and errors if the role/schema already exists. Do not run it against shared or production databases. Application calls and migrations use the `template` role, which owns its own schema and is not a PostgreSQL superuser.

Install dependencies using the updated lockfile as described in the [template README](../README.md). Set the connection URL through the environment or an ignored `.env`:

```powershell
$env:SERVICE_DATABASE_URL = 'postgresql+psycopg://template:local-demo-only@localhost:55404/telelink'
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check
.venv\Scripts\python.exe -m app.example --name demo-item
.venv\Scripts\python.exe -m app
```

`upgrade head` creates `template.example_items`; rerunning it is safe. The example CLI explicitly commits a transaction and reads the persisted row in a new session. Repeating the same example name reuses the row. The example model is a placeholder, not a patient record or a business API.

Percent-encode special characters in URL usernames/passwords. AWS uses an RDS endpoint, externally provided credentials and the required TLS configuration (for example `sslmode=verify-full` with a trusted RDS CA). Do not reuse local credentials on AWS.

## Sessions in request handlers

Use `get_session` with a synchronous handler so blocking database calls execute in FastAPI's thread pool:

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_session
from app.models import ExampleItem

@router.post('/example')  # Illustration only; add auth before exposing real writes.
def write_example(session: Session = Depends(get_session)):
    with session.begin():
        item = ExampleItem(name='synthetic-example')
        session.add(item)
        session.flush()
        item_id = item.id
    return {'id': str(item_id)}
```

The dependency closes the session and rolls back unfinished transactions; it does not silently commit. `session.begin()` commits on success and rolls back on an exception. Do not share sessions across requests or call synchronous SQLAlchemy directly in an async handler. Future workers create their own session/transaction per job.

## Adding a migration

1. Update only the owning service's models.
2. Ensure its database is at the current head.
3. Generate, inspect and commit a revision:

```powershell
.venv\Scripts\python.exe -m alembic revision --autogenerate -m 'describe schema change'
# Review generated upgrade/downgrade, defaults, constraints and data-loss implications.
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic check
```

Autogeneration compares only schema `template`, including removed tables in that schema; it must not propose changes to another service's schema. `alembic check` detects model/schema drift. Autogeneration is a starting point and cannot infer every rename/data migration.

To copy the template into a new service before its first deployment, change `SERVICE_SCHEMA` and the schema literals in its initial migration, then provision that service's role/schema. Keep its migration directory and version table independent. Do not edit already-applied migrations; add a revision instead. If the example has been deployed, remove it with a new reviewed migration.

For AWS, use controlled migration tasks and separate migration/runtime grants where practical. Runtime needs schema usage/table access, not schema ownership or cross-service writes. `upgrade` runs before accepting traffic, not on every ECS replica startup.

## Focused integration verification

Use only a disposable database with the `template` role/schema already provisioned:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://template:local-demo-only@localhost:55404/telelink'
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check app tests migrations
.venv\Scripts\python.exe -m ruff format --check app tests migrations
Remove-Item Env:TEST_DATABASE_URL
```

The integration test upgrades, writes/reads, verifies rollback, downgrades the example table, checks readiness failure, then upgrades again and checks metadata parity. It deletes example table data during downgrade. Never set `TEST_DATABASE_URL` to a shared development/demo/production database. Without the variable, the PostgreSQL integration test is explicitly skipped; other checks still run.

Stop the local container after use with `docker stop telelink-f04-postgres`. Removing that specifically named disposable container discards its data; no general volume/database reset is provided by this task.
