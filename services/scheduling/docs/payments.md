# S05/S06 payment processing and late recovery

Run migrations through `0006` before starting the workers. Scheduling owns its
inbox, confirmation outbox and `payment_recoveries` audit/delivery queue. No
billing tables or shared infrastructure/contracts are changed.

## Processing and recovery

The consumer validates `consultation_payment_succeeded.v1` through the M03 parser,
then retrieves the authoritative charge from billing. Payment, appointment,
tenant, patient, purpose and amount/currency must match the event and the trusted
appointment snapshot. Unbound holds and unverifiable facts retry/DLQ; they are
never acknowledged as handled. Restrict queue access to its EventBridge rule
and worker IAM role; the event source string is not authentication.

Slot-first locks serialize payment, expiry, cancellation, withdrawal and booking.
PostgreSQL `clock_timestamp()` after waiting determines expiry; event occurrence
and browser redirects do not determine payment timing. On-time pending payments
confirm atomically with inbox and `appointment_confirmed.v1` outbox insertion.
Repeated event IDs and different event IDs for the same charge have one effect.

At or after the hold deadline, expire outstanding holds under the same slot lock.
Recover the old appointment only if the slot is unreserved and not withdrawn,
its start remains future, and live tenant APIs report an active clinic and doctor.
Eligibility HTTP calls have the existing bounded tenant timeout; the slot lock
is held during these calls, and time is checked again afterwards. Tenant outages
roll back and retry, rather than treating an outage as inactive membership.
Expired Redis mirrors lapse at their original deadline; they cannot allocate or
release PostgreSQL capacity, and recovery never deletes another booking's key.

Successful recovery clears the appointment deadline and records its original
deadline, previous status, event ID and recovery time in `payment_recoveries`.
Unavailable/reallocated slots remain expired; cancelled appointments never reopen.
They expose `payment_resolution=refund_required` in existing authorized APIs,
retain succeeded payment truth, and queue the corresponding billing exception.
An earlier successful attempt may replace an unconfirmed bound payment. An extra
successful charge never replaces a confirmed payment or repeats confirmation;
only that extra charge is queued with `duplicate_charge` for refund review.
Cancelling a confirmed booking also queues its billing exception atomically.
A recovered booking's audit retains its recovery timestamp and original deadline
if subsequently cancelled, while its outcome/reason become refund-required.

The inbox, appointment, recovery decision and confirmation outbox commit together
before SQS acknowledgement. Billing flag delivery is separate: `--resolve` retries
committed exceptions with row locks and marks delivery only after a validated
billing acknowledgement. A timeout or local commit failure can repeat the remote
request, so billing must implement the contract's idempotent resolution operation.
Failed rows remain pending; last-attempt ordering lets later rows receive attempts.
Inspect pending rows and worker warnings when billing is unavailable. This flag
requests operator review; it does not call Stripe or issue an automatic refund.

## Billing adapter boundary

Billing is not implemented yet. These adapters use explicit synthetic payment
facts in tests; real billing/checkout/webhook/refund integration remains B02/B05/B07.
The scheduling-only HTTP client uses direct billing service paths:

- `GET /internal/payments/{payment_id}` returns C03 authoritative payment fields:
  payment/appointment/tenant/patient IDs, purpose, status and amount.
- `POST /internal/payments/{payment_id}/resolution` sends `resolution=refund_required`,
  `resource_id` (appointment ID), and C03 reason (`slot_reallocated`,
  `appointment_cancelled`, `appointment_unavailable`, or `duplicate_charge`).
  Return the matching succeeded consultation payment with `resolution=refund_required`,
  including on replay. Validate tenant, linked resource and scheduling caller;
  this endpoint must not start a provider refund or be exposed on public ingress.

Both requests use a short-lived HS256 JWT with issuer `telelink-service:scheduling`,
subject `scheduling`, audience `telelink-billing-scheduling`, integer issued/expiry
claims and a 60-second lifetime. Share a separate random secret only with billing.
Requests have a three-second timeout and do not follow redirects. HTTP is allowed
only in local/test settings; other environments require HTTPS. The contract's
external prefix is `/api/v1/billing`; the direct service adapter omits it, matching
the existing billing read adapter. Coordinate these receiving endpoints with B05.

Operator refund execution and later refunded-status synchronization require the
real billing implementation. Until that integration exists, retain refund_required
and arrange manual review; do not label a flag or delivered marker as a refund.

## Setup and operations

Set `SERVICE_DATABASE_URL`, `SERVICE_BILLING_URL`, `SERVICE_BILLING_SECRET`,
`SERVICE_TENANT_URL`, `SERVICE_SCHEDULING_SECRET` (existing tenant booking credential),
`SERVICE_PAYMENT_QUEUE_NAME`, `SERVICE_EVENT_BUS_NAME` and `SERVICE_AWS_REGION`.
The payment consumer requires tenant settings so late recovery cannot bypass
eligibility checks. API startup does not require billing settings.
For Floci set `SERVICE_AWS_ENDPOINT_URL=http://localhost:4566` and dummy SDK
credentials. On AWS omit endpoint overrides and use task-role credentials.

From `services/scheduling`, run three separate processes:

```powershell
.venv/Scripts/python.exe -m app.payment_worker
.venv/Scripts/python.exe -m app.payment_worker --publish
.venv/Scripts/python.exe -m app.payment_worker --resolve
```

`--once` processes one batch for any mode. The consumer polls SQS for five seconds;
independent publisher and resolution workers retry once a second. Migrations must
be run separately before workers. Downgrading `0006` deletes recovery audit and
pending billing deliveries: drain/export them first. Downgrading `0005` also drops
inbox/outbox history. Rollback never performs refunds.

## Verification

Payment and recovery tests cover exact deadline, guarded recovery, inactive or
withdrawn availability, membership removal, start time, billing/tenant failures,
competing bookings, cancellation, extra charges, duplicate deliveries and durable
billing flag retries. Billing reads/checkout/resolution remain labelled fixtures.
The opt-in Floci test verifies real EventBridge/SQS transport and confirmation
publication, not Stripe or AWS integration.

Local verification on 15 October 2026: all 217 scheduling tests passed with
PostgreSQL 17, Redis 7.4 and live Floci transport enabled for both on-time and
late recovery. Fresh/repeated upgrades, rollback/re-upgrade, model parity and
schema isolation passed, as did Ruff lint/format and `pip check`. Queue transport
is real; billing payment facts, checkout bindings and resolution acknowledgements
are explicit fixtures. Real billing/refund and AWS integration remain unverified.
