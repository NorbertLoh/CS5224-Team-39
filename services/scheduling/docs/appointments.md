# S04 appointment APIs

Direct routes omit the ingress prefix `/api/v1/scheduling`.

| Route | Behavior |
| --- | --- |
| GET `/appointments` | Current identity, C01 pagination: optional `tenant_id`, `status`, timezone-aware `from`/`to`; limit 1-100 (default 25), signed cursor. Ordered `(starts_at, appointment_id)`. |
| GET `/appointments/{appointment_id}` | Authorized C02 metadata, 200; missing or inaccessible resource returns identical 404. |
| POST `/appointments/{appointment_id}/cancel` | Body only `{reason}`: nonblank plain text, at most 2000 characters. Owning patient or active owning-clinic admin; 200. |
| POST `/internal/appointments/{appointment_id}/start` | Consultation service only; confirmed -> in_progress during `[starts_at,ends_at)`. |
| POST `/internal/appointments/{appointment_id}/complete` | Consultation service only; in_progress -> completed, no earlier than start. May finish after the slot end. |
| POST `/internal/appointments/{appointment_id}/no-show` | Scheduling operator only; confirmed -> no_show at/after end. |

## Read policy

SQL scopes rows before pagination using current identity `/me` records: patients see
their own appointments across clinics; active doctors see assigned appointments in
current clinic memberships; active clinic admins see owning-clinic appointments;
platform admins see operational metadata. Multiple roles combine permitted scopes.
Staff-only selection of an unrelated clinic returns 404. A patient clinic filter with
no own appointments returns an empty page. Subjects without an applicable role cannot
list appointments (403). Resource detail/cancel conceal unauthorized IDs with 404.

No clinical content, patient contact/address data or cancellation free text is returned.
Responses remain C03 metadata, including frozen price/payment linkage. Revocation removes
staff access on the next request; owning-patient access persists where their current
patient role authorizes it. Clinic suspension does not prevent historical reads or
cancellation. Arbitrary role/identity headers grant no access.

Cursors expire after 15 minutes and bind subject, current permission digest, selected
clinic, status and date filters. Permission/filter changes require a new page. Public
slot cursors cannot be used for appointments. Dates filter slot start: `from` inclusive,
`to` exclusive, positive interval when both are supplied. Appointment history has no
seven-day restriction. Elapsed held/pending deadlines display as `expired`, including
status-filtered lists, before worker persistence. Reads are snapshots and do not mutate
state or provide reusable authorization decisions.

## Cancellation and locks

Cancellation authorizes before taking mutation locks, then locks slot before appointment
and reloads the row after waiting. Elapsed holds persist as expired under these locks
before cancellation checks. Held/pending bookings can cancel before expiry. Confirmed
bookings can cancel only before start; payment resolution becomes `refund_required`
unless already refunded. Payment ID and price remain unchanged. This requests manual
refund review and never calls a payment provider.

Already-cancelled requests return the same resource without rewriting the original
reason, actor, time or updated timestamp. Expired, in-progress, completed and no-show
bookings return 409 `invalid_appointment_transition`. Deadline equality expires a hold;
start equality makes confirmed cancellation too late. Redis cleanup after commit
compares the old appointment ID, protecting replacement holds from delayed cleanup.
All expiry/withdrawal and future payment handlers must retain slot-first locking.

Migration `0004` adds nullable reason, verified actor UUID and UTC cancellation time
with a consistency constraint. API cancellation records all three atomically. Legacy
cancelled rows with all three null remain valid. These fields are private retained
metadata; no public response fields or cross-service foreign keys are added. Downgrade
to `0003` preserves appointments but removes these fields; export needed metadata first.

## Service callers and setup

Migrate scheduling to revision `0004`, preserving identity/tenant/Redis configuration.
Set separate random keys of at least 32 bytes: `SERVICE_CONSULTATION_SECRET` and
`SERVICE_OPERATOR_SECRET`, distinct from each other, the cursor key and tenant/scheduling
key. They are optional for public reads/cancellation; missing keys make the corresponding
internal action return 503. The `.env.example` keys are synthetic local examples only.

Service JWTs require HS256, integer `iat`/`exp`, positive lifetime at most 300 seconds:

| Caller | Issuer | Subject | Audience |
| --- | --- | --- | --- |
| Consultation | `telelink-service:consultation` | `consultation` | `telelink-scheduling-consultation` |
| Operator | `telelink-service:scheduling-operator` | `scheduling-operator` | `telelink-scheduling-operator` |

Cognito tokens, wrong service credentials/audiences and expired tokens cannot invoke
internal actions. Repeated start/complete/no-show after transition returns 409;
cancellation is explicitly idempotent. Ingress must exclude `/internal/*`; direct
service authentication also applies. Root routing/Compose are unchanged. These state
actions do not grant video admission; V02 still validates participants/payment/windows.

The authenticated billing checkout contract (held -> pending_payment) remains B02
integration. Verified payment confirmation is S05; late recovery and payment-resolution
events/audit are S06. No public PATCH sets arbitrary state, payment truth, IDs or prices.

## Verification

PostgreSQL/Redis checks cover source-scoped multi-role reads, revoked memberships,
tenant selection, private cursor binding/tied times, effective expiry, cancellation
metadata/idempotence/refund flags, credential separation, exact state/time boundaries
and cancellation/booking/start races. Existing S01-S03 checks also run.

The separate localhost-only HTTP check uses real Floci, identity, tenant and scheduling:

```powershell
$env:S04_COGNITO_CLIENT_ID='your-local-client-id'
$env:S04_DATABASE_URL='postgresql+psycopg://scheduling:local-demo-only@127.0.0.1:55411/telelink'
$env:S04_CONSULTATION_SECRET='same-local-key-configured-on-scheduling'
$env:S04_OPERATOR_SECRET='same-local-key-configured-on-scheduling'
services/scheduling/.venv/Scripts/python.exe dev/check_appointment_api.py
```

It creates two synthetic clinics and real HTTP holds, verifies read/cancel policy,
revocation, cancellation persistence/replay and suspended-clinic history. Confirmed
appointments are explicitly operator-seeded SQL fixtures for refund flags and internal
start/complete/no-show HTTP actions. This is not payment or video admission integration.
History is retained, memberships/tokens revoked and clinics suspended; no schema or
existing clinic is reset. The live check passed on 14 October 2026, along with S02/S03
HTTP regressions. Browser/UI and AWS checks remain unverified.

Local verification on 14 October 2026: 174 tests passed on PostgreSQL 17/Redis 7.4
with Python 3.10; Ruff lint/format and dependency checks passed. All three live
S02/S03/S04 HTTP checks passed, with the fixture boundary above retained explicitly.
