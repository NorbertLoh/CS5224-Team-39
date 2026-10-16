# S03 holds and reservations

POST `/appointments` (ingress prefix `/api/v1/scheduling`) accepts only
`{tenant_id, slot_id}` and returns the C03 appointment in `held` state, 201.
It requires a verified access token and the current identity's patient role.
Patient/doctor IDs, price, status, payment and deadline are server-controlled.
Unknown, foreign-tenant or withdrawn slots return 404; occupied, past or ineligible
slots return 409 `slot_unavailable`; inactive clinics return 409 `clinic_not_active`.
Extra body fields return 422. Missing Redis configuration returns 503.

Identity and tenant checks resolve current patient membership, active/provisioned
clinic, active doctor directory and trusted consultation price before database
locks. They are point-in-time checks across independent services: revocation or
suspension during an already admitted request is not atomically coordinated with
the scheduling commit. Future requests see the change. No fixtures or browser
identity headers authorize production requests.

## Transaction and clock

All reservation operations lock **slot first, appointment second**, with one slot
per transaction. Booking rechecks tenant/withdrawal under the slot row lock, then
reads PostgreSQL `clock_timestamp()` after lock acquisition. Expired held/pending
appointments become `expired` and flush before inserting a replacement. The same
transaction inserts the trusted price snapshot and sets
`hold_expires_at = min(server_now + 10 minutes, starts_at)`. Equality means expiry.
No checkout or retry extends the deadline. Repeated POST on a reserved slot
returns 409; S04 provides appointment recovery/listing, without a POST hold idempotency-key API.

Migration `0003` adds a partial unique index on slot ID for states `held`,
`pending_payment`, `confirmed`, `in_progress`. This protects capacity even for SQL
writers that do not use the API. Existing duplicate active reservations make
migration fail; reconcile them explicitly rather than discarding records. Downgrade
to `0002` removes the index and preserves rows; rollback through `0002` retains its
documented restriction on overlapping withdrawn history.

Withdrawal takes the same slot lock and expires elapsed holds before checking active
reservations. It either withdraws first and booking returns 404, or booking reserves
first and withdrawal returns 409. S04 cancellation/internal actions share these locks.
Future checkout/payment/confirmation code
must use this same lock order and recheck state/deadline under it. The index alone
does not enforce authorization, legal state transitions or withdrawn-slot eligibility
for arbitrary SQL writers. Avoid taking an appointment lock before its slot lock.

## Redis and failure handling

The private key `telelink:scheduling:hold:<slot_id>` contains only the appointment UUID.
Redis `PXAT` uses the persisted absolute deadline. Cache publication happens while
the slot lock is held, before commit, so an older request cannot overwrite a newer
reservation after releasing its lock. Expiry/rollback uses a Lua compare-and-delete:
old cleanup cannot delete a replacement hold's key.

PostgreSQL is authoritative. A missing, evicted, stale or expired Redis key cannot
free an unexpired database reservation or grant a booking. Reads use persisted
deadlines. Configured Redis outages log a generic warning and allow a safe database
hold to commit; readiness is 503 until Redis recovers. Redis failure/rollback may
leave an absent mirror or a transient ghost key, which is ignored for allocation
and expires by TTL. No distributed transaction or Redis notification is required.
The default Redis socket/connect timeout is 0.3 seconds, limiting time spent under
the slot lock. Heavy database contention can still time out and return 503.

## Setup and expiry worker

Install the updated lock file and local packages, then migrate scheduling to `0003`.
Configure `SERVICE_REDIS_URL` and optionally `SERVICE_REDIS_TIMEOUT_SECONDS`. Use
`redis://127.0.0.1:6379/0` for normal Compose Redis, or port 56379 for the dedicated
test container. Use `rediss://` with managed credentials outside local/test. Keep
URLs/credentials in environment or ignored `.env`, never committed real secrets.
Root Compose and frontend routing are unchanged.

From `services/scheduling`, run the API and worker in separate terminals with the
same service configuration:

```powershell
.venv/Scripts/python.exe -m app
.venv/Scripts/python.exe -m app.expire_holds
```

The worker runs bounded batches every five seconds, taking one slot per transaction
and skipping slot locks held by API requests or other workers. It persists expiry
even when Redis is unavailable. It does not depend on keyspace notifications and
can recover overdue holds after restart. For one batch:

```powershell
.venv/Scripts/python.exe -m app.expire_holds --once
```

Booking/withdrawal also perform lazy expiry, so allocation remains correct when the
worker is stopped. Run the worker for timely idle cleanup. No HTTP expiry bypass is
exposed. Deploy worker credentials scoped to scheduling's database schema and Redis
prefix. S04 handles cancellation. Payment success, late-payment exceptions and event publication
remain B02/S05/S06; Redis does not establish payment truth.

## Verification

The disposable PostgreSQL/Redis suite covers competing patients, expiry/reallocation,
withdrawal races, deadline equality, worker skip-lock behavior, Redis TTL loss/outage,
ownership-safe cache deletion, commit rollback, trusted context/prices, active
reservation uniqueness and migration isolation. No whole-database Redis reset occurs.

For a separate real Floci/three-service HTTP check, start local identity, tenant,
scheduling and Redis, then from the repository root export these local-only values:

```powershell
$env:S03_COGNITO_CLIENT_ID='your-local-client-id'
$env:S03_DATABASE_URL='postgresql+psycopg://scheduling:local-demo-only@127.0.0.1:55411/telelink'
$env:S03_REDIS_URL='redis://127.0.0.1:6379/0'
services/scheduling/.venv/Scripts/python.exe dev/check_booking_holds.py
```

The check creates one new synthetic clinic, assigns its doctor through identity and
verifies four simultaneous holds yield one success, reads real PostgreSQL/Redis,
deletes only its own cache key to prove capacity remains reserved, and observes an
eight-second slot-bound TTL expire before running the actual expiry worker once.
Doctor membership/tokens are revoked and the clinic is suspended afterward. Appointment
history is retained; the longer hold expires normally with the worker. No existing
clinic or schema is reset. Browser/UI, AWS/RDS/managed Redis and payment workflows
remain unverified.

Verified on 14 October 2026: 127 tests passed with PostgreSQL 17, Redis 7.4 and
Python 3.10; Ruff lint/format and dependency checks passed. Both the S02 real
HTTP regression and the S03 real Floci/three-service/PostgreSQL/Redis hold and
expiry check passed. These checks establish local reservation/expiry behavior,
not payment confirmation, AWS compatibility or atomic cross-service revocation.
