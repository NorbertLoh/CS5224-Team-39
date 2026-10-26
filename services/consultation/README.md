# Consultation sessions and admission (V01/V02)

Consultation owns PostgreSQL schema `consultation`, its own Alembic version table,
and one session per appointment. UUID links to scheduling and identity are opaque;
there are no cross-service foreign keys or reads. The schema stores tenant,
appointment, patient, doctor, scheduled UTC interval, state and lifecycle times.
It contains no clinical notes, raw credentials, media or recordings. V02 adds
hashed, single-use admission leases; see [ADMISSION.md](ADMISSION.md) for API,
service authentication, setup and observed verification.

## Lifecycle rules

`scheduled -> in_progress -> completed` is the only state progression. Session
creation is idempotent by appointment ID; different tenant, participant or schedule
snapshots for the same appointment fail with `session_context_conflict` (409).
The snapshot is immutable. Scheduling retains cancellation/no-show ownership;
V02 rejects those actual appointment states before using a session.

| Operation | Rule |
| --- | --- |
| Join/rejoin eligibility | Scheduled: `[starts_at - 10 minutes, ends_at)`; in progress: from the opening time until doctor completion |
| Start | Assigned doctor, scheduled state, `starts_at <= server_now < ends_at` |
| End | Assigned doctor, in_progress state, `server_now >= started_at` |
| Retry start/end | Same resulting state returns original timestamps; no duplicate transition |
| Completed | No join, restart or reopening |

For a 10:00–10:30 appointment, joining opens exactly at 09:50. Early joining is a
waiting-room allowance and does not start the session. If the doctor has not
started the consultation, joining closes at 10:30. Once in progress, participants
can leave and rejoin after 10:30 until the doctor explicitly ends it. End is
allowed after the scheduled end; there is no automatic expiry/completion worker.
Every admission still checks current participant access, membership and payment,
and each lease retains its short expiry. Completing the session blocks further
admission and lease checks.

`ensure_session` and `transition` use PostgreSQL row locks and caller-owned
transactions. Rollbacks leave no partial transition. The database enforces
appointment uniqueness, valid state/timestamp combinations, legal transitions,
immutable context and immutable previously recorded lifecycle timestamps.
Use the service role, not a database superuser. No row-level security is claimed.

## Integration boundary

End consultation first finalizes any saved prescription through clinical records
using the assigned doctor's access token. It verifies the returned appointment
context before persisting the local end and synchronizing scheduling completion.
It then finalizes the saved MC decision. A prescription failure leaves the
consultation in progress; a lost response can be retried without duplicate
issuance. Completed visits can retry the same workflow to recover an existing
unissued draft and finish the MC handoff. This is a sequence of idempotent service
operations, not a transaction spanning services. Deploy updated clinical records
before consultation. No migrations or new settings are required.

The lifecycle functions are internal Python operations. V02 exposes admission
HTTP endpoints, described separately in ADMISSION.md. The tenant/doctor parameters must come from validated
server context. `can_join` evaluates time/state only; it is **not authorization**.
`now` is a trusted clock injection for tests, never a client-supplied timestamp;
omitting it uses server UTC after acquiring the lifecycle row lock.

V02 authenticates callers, resolves current membership and actual appointment
participants/payment/state, builds the trusted snapshot and issues short-lived
admission. Admission never starts or completes an appointment. The later video
lifecycle integration must coordinate scheduling start/complete with durable
retry/reconciliation; no cross-service atomic transaction is claimed. V03/V04
retain PeerServer wiring and browser integration. No video/provider/AWS integration
is completed by these local service checks.

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
