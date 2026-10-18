# Consultation sessions (V01)

Consultation owns PostgreSQL schema `consultation`, its own Alembic version table,
and one session per appointment. UUID links to scheduling and identity are opaque;
there are no cross-service foreign keys or reads. The schema stores tenant,
appointment, patient, doctor, scheduled UTC interval, state and lifecycle times.
It contains no clinical notes, credentials, media or recordings.

## Lifecycle rules

`scheduled -> in_progress -> completed` is the only state progression. Session
creation is idempotent by appointment ID; different tenant, participant or schedule
snapshots for the same appointment fail with `session_context_conflict` (409).
The snapshot is immutable. Scheduling retains cancellation/no-show ownership;
V02 must reject those actual appointment states before using a session.

| Operation | Rule |
| --- | --- |
| Join/rejoin eligibility | `[starts_at - 10 minutes, ends_at)` in scheduled/in_progress state |
| Start | Assigned doctor, scheduled state, `starts_at <= server_now < ends_at` |
| End | Assigned doctor, in_progress state, `server_now >= started_at` |
| Retry start/end | Same resulting state returns original timestamps; no duplicate transition |
| Completed | No join, restart or reopening |

For a 10:00–10:30 appointment, the window opens exactly at 09:50 and closes exactly
at 10:30. Early joining is a waiting-room allowance and does not start the session.
Disconnect/leave does not end it: participants can rejoin during the window until
the doctor explicitly ends it. End is allowed after the scheduled end so a delayed
completion can still be recorded; there is no automatic expiry/completion worker.
An in-progress session after `ends_at` cannot obtain fresh join eligibility.
Retrying start after the window only acknowledges an existing transition; it
does not grant admission. Existing media termination at the deadline is a later
video integration concern, not something this persistence layer enforces.

`ensure_session` and `transition` use PostgreSQL row locks and caller-owned
transactions. Rollbacks leave no partial transition. The database enforces
appointment uniqueness, valid state/timestamp combinations, legal transitions,
immutable context and immutable previously recorded lifecycle timestamps.
Use the service role, not a database superuser. No row-level security is claimed.

## Integration boundary

These are internal Python domain functions, with no HTTP endpoints or application
authentication bypass. The tenant/doctor parameters must come from validated
server context. `can_join` evaluates time/state only; it is **not authorization**.
`now` is a trusted clock injection for tests, never a client-supplied timestamp;
omitting it uses server UTC after acquiring the lifecycle row lock.

V02 must authenticate callers, resolve current membership and actual appointment
participants/payment/state, build the trusted snapshot and issue short-lived
admission. It must coordinate scheduling's authenticated start/complete operations
with durable retry/reconciliation rather than claiming a cross-service atomic
transaction. No scheduling transition is made by V01. V03/V04 own signalling and
browser integration. No real admission, payment or video integration is claimed.

## Local setup

Use Python 3.10+ and PostgreSQL (CI uses 17). From this directory, with a virtual
environment active:

```powershell
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
# Run once as a local PostgreSQL administrator against synthetic database telelink:
psql -U postgres -d telelink -v ON_ERROR_STOP=1 -f scripts/create-local-schema.sql
$env:SERVICE_DATABASE_URL='postgresql+psycopg://consultation:local-demo-only@localhost:5432/telelink'
python -m alembic upgrade head
python -m alembic check
```

The administrator provisions the restricted service role and schema before
migration. Replace the demo password outside local synthetic development. Run
migrations once per environment with the service schema owner, not per replica.
No Compose/routing changes are needed for this domain-only increment. Alembic only
inspects/migrates consultation; it does not create/drop another service's schema.

## Verification

Against a **disposable** database provisioned with the role/schema above and
`tests/isolation-fixture.sql` (run the fixture as administrator):

```powershell
$env:TEST_DATABASE_URL=$env:SERVICE_DATABASE_URL
$env:CONSULTATION_TEST_ALLOW_RESET='1'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Tests downgrade/remove all consultation tables in that database, then re-upgrade.
They verify migration idempotency/model parity, an unrelated sentinel's survival
and write isolation, exact window boundaries, lifecycle persistence, context
conflicts, concurrent creation/start/end, rollback, terminal-state protection,
and direct SQL constraint enforcement. Without TEST_DATABASE_URL, database checks
skip; that does not establish persistence correctness. AWS/video verification
remains outside V01.
