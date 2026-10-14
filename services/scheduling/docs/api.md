# S02 availability API

Direct service routes omit the ingress prefix `/api/v1/scheduling`.

| Route | Behavior |
| --- | --- |
| POST `/clinics/{tenant_id}/slots` | Active member doctor, active/provisioned clinic. Body contains only `starts_at`, `ends_at`. Future 30-minute slot, 201. Server resolves doctor from current identity and indicative SGD price from tenant. Overlap across clinics returns 409 `slot_overlap`. |
| GET `/clinics/{tenant_id}/slots` | Public active/provisioned clinic. Required timezone-aware `from`, `to`, positive interval up to seven days; optional `doctor_id`, `limit=1..100` (default 25), `cursor`. Returns `{items, next_cursor}`, ordered `(starts_at, slot_id)`. |
| DELETE `/slots/{slot_id}` | Owning doctor with current active membership, 204. Active appointment reservation returns 409 `slot_reserved`; missing, withdrawn or unauthorized slot returns 404. Withdrawal is permitted in a suspended clinic because it removes availability. |

The public list selects future, non-withdrawn slots whose start falls in `[from,to)`.
It filters against tenant's live, paginated active-doctor directory before applying
slot pagination. Unknown/ineligible doctor filters return an empty page. Inactive
clinics are hidden with 404; slot creation returns 409 `clinic_not_active`.
Cursor signatures expire after 15 minutes and bind clinic, doctor filter and date
window. Equivalent timezone representations normalize to UTC. Limits may change
between pages. C01 timestamps serialize to UTC with milliseconds.

Responses include only C03 slot ID/tenant/doctor/times, availability and indicative
price. They never expose patient IDs, reservation owners, payment references or
appointment contents. Current price comes from tenant on every request, with no
browser price override. Appointment price snapshots remain unchanged.

Authenticated actions verify Cognito RS256 access tokens using the shared strict
verifier, then call identity `/me` for current subject/memberships. No role groups,
arbitrary identity headers or fixtures grant permission. Scheduling calls tenant's
internal booking profile with a 60-second HS256 service JWT (issuer
`telelink-service:scheduling`, audience `telelink-tenant-booking`, subject
`scheduling`). Missing configuration, timeouts and upstream failures fail closed;
malformed/mismatched upstream data returns a safe 502. C01 errors include request IDs.

## Runtime setup

Follow [schema setup](../README.md) and [identity/tenant setup](../../../docs/clinic-backend.md).
Keep reset-enabled tests on their dedicated disposable database. For persistent
local integration, provision scheduling's role/schema once in the existing
`telelink-clinic-postgres` development container, then migrate using scheduling's
role and port 55411. The provisioning script only creates scheduling's schema/role
and shared `btree_gist`; it does not modify identity or tenant tables.

Copy `.env.example` to `.env`, set its database URL, and replace Cognito pool/client
values with the same values used by identity. Set `SERVICE_SCHEDULING_SECRET` to
tenant's existing scheduling secret; generate a different cursor key of at least
32 bytes. Preserve existing tenant/identity keys. URLs use localhost for host
processes and service names for containers; use HTTPS, real Cognito and managed
secrets outside local/test. CORS accepts explicit origins.

From `services/scheduling`:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://scheduling:local-demo-only@127.0.0.1:55411/telelink'
.venv/Scripts/python.exe -m alembic upgrade head
Remove-Item Env:SERVICE_DATABASE_URL
.venv/Scripts/python.exe -m app
```

The service defaults to port 8003. `/health/live` checks process health;
`/health/ready` checks required configuration, readable tables, revision `0005`
and Redis connectivity. It does not probe identity/tenant; actual operations handle their failures.
Swagger is `/docs`. No root Compose, frontend proxy or routing changes are part of
S02; use port 8003 directly until the relevant integration task wires them up.

## Booking boundary

Held, pending-payment, confirmed and in-progress appointments mark slots unavailable
and block withdrawal. Cancelled/expired/completed/no-show history can be retained
under a withdrawn slot. DELETE locks the slot row before checking reservations and
marking withdrawal. S03 booking/expiry uses that same slot lock, rejects withdrawn
slots and enforces active-reservation uniqueness in PostgreSQL. Withdrawal expires
any elapsed holds under this lock before checking remaining reservations.

Availability creation takes a per-doctor PostgreSQL transaction advisory lock
across clinics before inserting. This prevents simultaneous overlapping GiST
inserts from deadlocking and lets the losing request return `slot_overlap`.
The database exclusion constraint remains the final guard, including direct SQL.

The list treats held/pending appointments as unavailable only before their persisted
deadline; confirmed/in-progress reservations remain unavailable. S03 expires elapsed
holds transactionally before reallocation. Redis TTL alone will not release capacity.
Listing remains a snapshot. See [holds](holds.md) for the expiry worker, Redis failure
behavior and booking limits, and [appointments](appointments.md) for S04 reads and
transitions. Checkout/payment confirmation and late recovery remain B02/S05/S06.
No AWS/RDS claim is made from these local checks.

## Verification

PostgreSQL tests cover real storage, migrations/model parity, concurrent duplicate
slot creation, cross-clinic overlaps, token/role/tenant failures, current membership
revocation, reservation blocking, history preservation, pagination/filter binding,
validation, upstream failures and safe rollback refusal for overlapping history.
The HTTP adapters use signed credentials with mocked responses in unit tests.

A separate real HTTP check uses all four seeded Floci accounts and running identity,
tenant and scheduling services. From the repository root:

```powershell
$env:S02_COGNITO_CLIENT_ID='your-local-client-id'
services/scheduling/.venv/Scripts/python.exe dev/check_scheduling_integration.py
```

It creates two uniquely named synthetic clinics, assigns the doctor through identity,
creates/lists/withdraws slots, verifies role gates, cross-clinic overlap, live price
updates, immediate revocation filtering and inactive-clinic rejection. Created clinics
remain suspended for inspection; new doctor memberships and acquired refresh tokens
are revoked. It never resets schemas or changes pre-existing clinics. It uses only
fixed localhost endpoints and synthetic Floci credentials.

On 14 October 2026, all 94 local tests, Ruff lint/format and `pip check` passed;
the real Floci/three-service HTTP check also passed. Browser/UI integration
and AWS deployment remain unverified.
