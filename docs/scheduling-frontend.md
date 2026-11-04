# Scheduling frontend (S07)

The doctor availability editor, clinic booking and patient/doctor/clinic appointment
pages use real scheduling APIs. No runtime fixture schedule, account selector,
fabricated appointment ID or client-set payment state is used.

RF10 updates appointment browsing for all three roles to shared Upcoming/Past
cards across dates, with server-side period filtering and independent pagination.
Current behavior and historical RF10 evidence are consolidated below.

## Local setup

Start identity and tenant using [clinic backend setup](clinic-backend.md). Configure
scheduling using [its API setup](../services/scheduling/docs/api.md), with the same
Cognito pool/client and tenant scheduling key, a separate cursor key, PostgreSQL
schema migrations through the current Alembic head, and Redis. Keep local configuration in ignored
`.env` files. Start scheduling and its expiry worker from `services/scheduling`:

```powershell
.venv/Scripts/python.exe -m app
.venv/Scripts/python.exe -m app.expire_holds
```

Start Vite with `npm run dev` from `apps/web`. The
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
  Upcoming/Past tabs, detail polling and refresh. Patients see their own rows, doctors
  their assigned rows, and clinic admins their selected owning clinic. The backend
  remains authoritative. Cells and details show the patient, doctor and clinic
  names that scheduling captured at booking (migration `0007`). Appointments booked
  earlier may have no names; public directory fallbacks and readable labels handle
  missing clinic/doctor/patient names. Cancellation is
  offered to the patient/clinic admin for eligible states; the server rechecks time,
  ownership and transitions. Refund review remains separate from payment truth.
- Booking/list/detail refresh after scheduling writes. Queries use identity/session
  and clinic context; identity failures hide protected controls. Reads can refresh
  on focus; appointment/hold polling reflects expiry and payment events.
- Billing checkout is connected through B07's authenticated checkout/status APIs;
  [billing setup](B07-live-billing.md) documents the provider callback path. Payment
  state comes from services. Clinic consultation refunds use
  [the billing refund flow](../services/billing/REFUNDS.md), and video entry uses
  [booked consultation admission](V04-booked-video.md). AWS verification remains separate.

## Appointment periods (RF10)

All three role workspaces default to Upcoming and show each booking once with its
Singapore date/time range. The overall clinic-admin view has a clinic selector;
clinic-specific routes are fixed to that clinic. Changing period or clinic clears
the selected details. Each tab has independent loading/error/empty states, cursor
pagination and a count of loaded records, not a claimed total. Lists poll every
15 seconds and retain existing detail actions.

`GET /appointments?period=upcoming` returns active `held`, `pending_payment`,
`confirmed` and `in_progress` rows whose end is later than server time, ordered by
start time then ID ascending. Effective hold expiry is applied first. `period=past`
returns the complement, including cancelled/completed/expired/no-show bookings
regardless of scheduled date, ordered by start time then ID descending. Expiry
and classification share a statement timestamp within each SQL query.

Filtering occurs before pagination. Cursors bind period/direction; cross-period
or filtered/unfiltered reuse returns 422. Omitting `period` preserves the ascending
list contract for other clients. Patient ownership, doctor assignment, selected
clinic and current membership checks remain authoritative in scheduling.
No migration or new configuration was introduced by RF10; host users updating
that change restart scheduling. Booking, payment, refund and admission rules remain.

## Verification

From `apps/web`: `npm run lint`, `npm run typecheck`, `npm run build`.
RF04 removed frontend fixture/test harnesses; there is no frontend `npm test`
script. Use existing service checks and explicitly scoped live walkthroughs for
runtime evidence. Reset-enabled service tests require disposable PostgreSQL.

Regenerate wire types from scheduling's Pydantic/OpenAPI models from the repo root:

```powershell
services/scheduling/.venv/Scripts/python.exe dev/export_scheduling_types.py
```

Preserve the generated file's existing formatting (single quotes, no semicolons)
and run frontend lint/typecheck after regeneration. No service startup or
credentials are needed to export the types.

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

### Historical S07 evidence (15 October 2026)

At implementation time, 60 frontend tests, lint and production build passed. Both Python
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
assets path. AWS and billing were unverified by that run. Later booking/payment
integration is recorded in [I01](I01-local-journey.md); S08/Q02 readiness/contention
work is recorded in [Q02 verification](Q02-booking-verification.md).

### Historical RF10 evidence (23 October 2026)

RF10 merged in [PR #274](https://github.com/NorbertLoh/CS5224-Team-39/pull/274);
[issue #273](https://github.com/NorbertLoh/CS5224-Team-39/issues/273) is closed.
55 appointment/period API checks passed; two Redis-dependent checks were skipped
locally. Ruff and frontend lint/typecheck/build passed. Checks covered effective
expiry, active/ongoing/terminal classification, both page directions, timestamp
ties, cursor rejection and role/membership scope.

Actual Tailscale API checks verified periods, ordering, pagination and scope for
patient, doctor and clinic-admin accounts. Browser checks covered clinic-admin
empty states, descending Past cards, selection/reset, clinic switching, the
clinic-specific route without a selector, one Upcoming booking with full SGT times
and keyboard tab switching. Scheduling readiness remained HTTP 200 after restart.
No business-data reset or provider operation occurred. This is retained historical
evidence, not a cleanup-phase verification run.
