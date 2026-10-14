# Scheduling service (S01-S03)

S01 creates scheduling-owned fixed availability slots and appointments following
[C02](../../contracts/identity-clinic-access.md) and
[C03](../../contracts/booking-payment.md). S02 implements doctor slot creation,
withdrawal and public slot listing with current identity/tenant access checks.
S03 adds patient appointment holds, PostgreSQL active-reservation uniqueness and
atomic expiry/reallocation, plus expiring Redis mirrors and a cleanup worker.
See [availability API](docs/api.md) and [hold setup and verification](docs/holds.md).
Appointment list/detail/cancel and payment workflows remain S04-S06.

## Schema

All tables and the Alembic version table live in `scheduling`. The service role
owns this schema only; migration reflection excludes other schemas. External
clinic, doctor, patient and payment UUIDs have no cross-service foreign keys.

`availability_slots` stores UUID slot/tenant/doctor IDs, UTC start/end timestamps
and creation time. Slots are finite 30-minute half-open intervals `[start, end)`.
A GiST exclusion constraint prevents overlap for a doctor across all clinics;
adjacent slots and simultaneous slots for different doctors are allowed. An
administrator provisions PostgreSQL's `btree_gist` extension once in `public`.
It is shared infrastructure and is never dropped by service migrations.

`appointments` stores C03 participant IDs, slot/time context, state, persisted
hold deadline, trusted consultation price snapshot (integer minor units, SGD),
payment ID/resolution and UTC creation/update timestamps. A composite foreign
key verifies the tenant, doctor and times against the referenced slot. Slot
deletion is restricted while appointments refer to it, preserving history.
Triggers protect slot context, appointment links, price and hold deadline from
changes, preserve creation timestamps and refresh appointment update time for
both ORM and direct SQL writes. A confirmed appointment clears its deadline;
expired/cancelled holds retain it for audit.

Checks constrain C03 states/resolutions, safe nonnegative money and hold deadlines
(after creation, at most ten minutes, no later than slot start). Tenant/doctor/
patient time indexes support C01 pagination; a partial expiry index supports
future hold cleanup. Slot availability is derived by S02/S03, rather than stored
as a stale boolean. Current indicative prices come from tenant; appointments
store the price revalidated when a hold is created.

S01 validates stored values and context. S02 enforces future slot creation,
active clinic/doctor eligibility and authorization. S03's partial unique index
allows one held/pending-payment/confirmed/in-progress appointment per slot.
Booking, expiry and withdrawal share the slot-first transaction lock order.
Historical appointments remain permitted. PostgreSQL deadlines govern expiry;
Redis TTLs cannot release database capacity. S04-S06 implement appointment reads,
cancellation, checkout, confirmation, recovery and audit events. S03 creates holds;
payment integration is not implemented here.

## Fresh local setup (PowerShell)

From `services/scheduling`, with Python 3.10+ and Docker Desktop:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
docker run --name telelink-s01-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=s01-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55412:5432 -d postgres:17
docker exec telelink-s01-postgres pg_isready -U postgres -d telelink
```

Wait for `accepting connections`. Provision once on a fresh database:

```powershell
Get-Content -Raw scripts/create-local-schema.sql | docker exec -i telelink-s01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
$env:SERVICE_DATABASE_URL = 'postgresql+psycopg://scheduling:local-demo-only@127.0.0.1:55412/telelink'
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check
```

Provisioning deliberately fails if the service role/schema already exists.
Use `docker start telelink-s01-postgres` to reuse this container; repeat upgrades
are safe. Alembic requires the exported URL and does not load `.env`. The shared
engine configures UTC and `search_path=public`; ORM tables are schema-qualified.
S02 migration `0002` adds nullable `withdrawn_at` and applies the overlap constraint
only to non-withdrawn slots. Withdrawal preserves cancelled/expired/completed
appointment history and permits replacement availability. A downgrade through
`0002` restores S01's stricter overlap rule: if replacement slots overlap withdrawn
history, PostgreSQL rejects the rollback atomically. Reconcile those rows explicitly
or restore an earlier backup before rollback; the migration never deletes history
to make it fit. On compatible data, `alembic downgrade base` deletes scheduling
tables/functions, retaining the schema/version table and shared extension.

Root Compose, routing and API contracts are unchanged. Deployment must provision
`btree_gist` before migration, provide managed credentials/TLS and separate
runtime/migration grants, and serialize migrations as described in
[F04](../template/docs/database.md). Real AWS/RDS verification remains untested.

## Focused verification

Use a **disposable database**: tests downgrade and recreate scheduling tables.
Create the read-only sentinel once as administrator to check isolation:

```powershell
Get-Content -Raw scripts/create-test-sentinel.sql | docker exec -i telelink-s01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
$env:TEST_DATABASE_URL = $env:SERVICE_DATABASE_URL
$env:TEST_REDIS_URL = 'redis://127.0.0.1:56379/0'
$env:SCHEDULING_TEST_ALLOW_RESET = '1'
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
```

The service-specific CI runs these checks on PostgreSQL 17 with Python 3.10.
S03 also uses real Redis 7.4. Start its dedicated test container once with
`docker run --name telelink-s03-redis -p 127.0.0.1:56379:6379 -d redis:7.4-alpine`.
Tests remove only their own randomly identified cache keys, never the whole Redis DB.
Tests verify fresh/repeated upgrades, downgrade/re-upgrade, Alembic model parity,
overlap/duration constraints, slot context, price/deadline guards, immutable
fields, timestamp updates, history retention and schema isolation.

Local verification on 14 October 2026: 45 tests passed on PostgreSQL 17 with
Python 3.10 in a fresh scheduling virtual environment; Ruff lint/format and
`pip check` passed. AWS/RDS compatibility and booking concurrency are unverified.
