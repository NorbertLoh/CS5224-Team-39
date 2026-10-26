# Scheduling frontend (S07)

The doctor availability editor, clinic booking and patient/doctor/clinic appointment
pages use real scheduling APIs. No runtime fixture schedule, account selector,
fabricated appointment ID or client-set payment state is used.

RF10 updates appointment browsing for all three roles to shared Upcoming/Past
cards across dates, with server-side period filtering and independent pagination.
See [RF10 behavior and verification](RF10-appointment-periods.md).

## Local setup

Start identity and tenant using [clinic backend setup](clinic-backend.md). Configure
scheduling using [its API setup](../services/scheduling/docs/api.md), with the same
Cognito pool/client and tenant scheduling key, a separate cursor key, PostgreSQL
schema migrations through `0007`, and Redis. Keep local configuration in ignored
`.env` files. Start scheduling and its expiry worker from `services/scheduling`:

```powershell
.venv/Scripts/python.exe -m app
.venv/Scripts/python.exe -m app.expire_holds
```

Start Vite with `npm run dev` from `apps/web`. The new
`/api/v1/scheduling` proxy defaults to `http://127.0.0.1:8003`; optionally set
`SCHEDULING_API_TARGET` in `apps/web/.env` and restart Vite. AWS mode uses the
existing `VITE_AWS_API_BASE_URL` plus `/scheduling`; configure authenticated gateway
routing separately. Internal scheduling routes are rejected by the local proxy. Vite proxy configuration applies only to local development.
There are no Compose, API/event contract or infrastructure changes.

## Behavior and boundaries

- Doctor availability uses identity `/me` and current active doctor memberships.
  A clinic-specific route keeps that clinic selected. All slot pages in the visible
  Singapore week are loaded. Add/remove writes use the existing server contracts;
  each slot is a separate transaction. A failed batch reports saved changes and
  refreshes the schedule. The server enforces cross-clinic overlaps and reservation
  protection. The selected clinic's public slot API cannot list suspended clinics.
- Booking loads actual slots for any selected current/future Singapore date. The
  server owns doctor/patient, price snapshot, reservation ID, state and expiry.
  Duplicate booking and stale-slot conflicts surface without automatic POST retries.
  The hold review polls server detail, counts down to the persisted deadline, and
  releases an active booking before changing time. Leaving the page preserves the
  booking for recovery through Appointments.
- Role workspaces list current authorized appointments with cursor pagination,
  date selection, detail polling and refresh. Patients see their own rows, doctors
  their assigned rows, and clinic admins their selected owning clinic. The backend
  remains authoritative. Cells and details show the patient, doctor and clinic
  names that scheduling captured at booking (migration `0007`). Appointments booked
  earlier have no names, so they show the identifiers instead. Cancellation is
  offered to the patient/clinic admin for eligible states; the server rechecks time,
  ownership and transitions. Refund review remains separate from payment truth.
- Booking/list/detail refresh after scheduling writes. Queries use identity/session
  and clinic context; identity failures hide protected controls. Reads can refresh
  on focus; appointment/hold polling reflects expiry and payment events.
- Billing checkout is B07. The live hold review explicitly says billing is not
  connected; it never fabricates pending-payment, confirmed or paid states. Payment
  result screens, refunds, consultation admission and AWS verification are separate
  tasks.

## Verification

From `apps/web`: `npm test`, `npm run lint`, `npm run build`.
Focused tests cover authenticated minimal payloads, public slot pagination, clinic
and cursor binding, hold conflicts without retries, membership-derived UI, exact
cancellation deadlines, real hold display, and role-specific cancellation controls.
Earlier fixture helpers remain test-only; production display helpers are separate.

Regenerate wire types from scheduling's Pydantic/OpenAPI models from the repo root:

```powershell
services/scheduling/.venv/Scripts/python.exe dev/export_scheduling_types.py
```

Format the generated file with the feature's documented Prettier 3.6.2 options
(single quotes, no semicolons). No service startup or credentials are needed.

The real adapter check is:

```powershell
services/identity/.venv/Scripts/python.exe dev/check_scheduling_frontend.py
```

It uses real local Floci PKCE sessions and runs the actual TypeScript adapters
through Vite to identity, tenant, scheduling, PostgreSQL and Redis. It creates two
new synthetic clinics and doctor memberships, adds/reads slots, creates trusted
holds, rejects duplicate holds and doctor cancellation/reserved withdrawal, reads
patient/doctor/clinic lists/details, cancels idempotently and verifies release.
Cleanup cancels its bookings, withdraws its slots, revokes its memberships/tokens and
suspends its clinics. Appointment history is retained; no existing clinic or schema
is reset. This is a mutating local test, not a browser or billing integration test.

Current evidence: 60 frontend tests, lint and production build passed. Both Python
helpers pass Ruff; the TypeScript live-check script passes static type checking.
Real Floci sign-in and the Vite identity
proxy returned 200. Read-only real TypeScript adapters through Vite passed for
patient, doctor and clinic identity/list calls; existing patient and clinic detail
reads also passed. Internal ingress returned 404 and protected API errors retained
JSON responses rather than falling through to the SPA. On 15 October 2026, after
explicit user approval, the real mutating adapter check passed with exit code 0,
including cancellation/slot withdrawal, membership/token revocation and clinic
suspension cleanup. GitHub CI passed for the implementation. Browser interaction
is unverified: browser automation initialization failed twice with a missing kernel
assets path. AWS and billing remain unverified.

Suggested follow-up discovered during setup: scheduling readiness compares the
migration revision to `0005`, while S06's current head is `0006`. This can report 503
on a fully migrated database; investigate the readiness check in a separate task.
No backend fix is included in S07.
