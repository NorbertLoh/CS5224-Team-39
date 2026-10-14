# S05 payment event consumer

Run migration `0005` before starting the worker. It creates scheduling-local
`event_inbox` and `event_outbox`; downgrade drops their deduplication/publication
history. Drain pending publications and retain/export history before rollback.
No billing tables or shared infrastructure files are changed.

## Processing

The payment worker consumes only `consultation_payment_succeeded.v1` from the
configured scheduling queue. The M03 parser validates the C05 source, event
type, version and envelope. Queue access must be restricted to the intended
EventBridge rule and worker IAM role; the source string alone is not a signature.

Before locking a reservation, the handler retrieves the payment from billing.
It verifies succeeded status, consultation purpose, payment/appointment/tenant/
patient IDs, and amount/currency against both the event and appointment snapshot.
The payment must already be bound by trusted checkout and the appointment must
be `pending_payment`. S05 does not implement B02's checkout reservation API.

It then locks slot before appointment and reads PostgreSQL `clock_timestamp()`
after waiting. Strictly before the persisted deadline it changes the appointment
to `confirmed`, sets payment resolution to `confirmed`, clears the hold deadline,
and stages `appointment_confirmed.v1` with the input correlation ID. The inbox,
appointment and outbox commit in one transaction; SQS acknowledgement follows.
PostgreSQL remains the reservation authority. The old Redis mirror expires at
its original deadline and cannot free a confirmed database reservation.

Replayed event IDs skip processing. A different event ID for the same already
confirmed payment also emits no second confirmation and never regresses an
in-progress/completed/no-show appointment. Incorrect contexts, billing outages,
unbound holds, cancellation and expired deadlines roll back and remain on the
queue for bounded retry/DLQ. They never steal a newer reservation. Late-success
recovery/refund coordination is S06; this PR does not acknowledge it as handled.

## Billing adapter boundary

The billing service is not implemented yet. This feature includes a fail-closed
HTTP adapter and tests with synthetic payment facts, not a working Stripe flow.
Billing must provide `GET /internal/payments/{payment_id}` (direct service path)
to return its authoritative payment record with C03 fields `payment_id`,
`appointment_id`, `tenant_id`, `patient_id`, `purpose`, `status` and `amount`.
The service must validate a scheduling-only HS256 JWT:

| Claim | Value |
| --- | --- |
| issuer | `telelink-service:scheduling` |
| subject | `scheduling` |
| audience | `telelink-billing-scheduling` |
| issued/expiry | integer Unix seconds, client uses a 60-second lifetime |

Use a separate random secret shared only by scheduling and billing. The adapter
does not follow redirects and uses a three-second timeout. Only local/test may
use HTTP; other environments require HTTPS. Coordinate the receiving endpoint
and authentication with B05 before claiming real billing integration.

## Setup

Set `SERVICE_DATABASE_URL`, `SERVICE_BILLING_URL`, `SERVICE_BILLING_SECRET`,
`SERVICE_PAYMENT_QUEUE_NAME` (local default `telelink-local-scheduling`),
`SERVICE_EVENT_BUS_NAME` and `SERVICE_AWS_REGION`. For Floci only, also set
`SERVICE_AWS_ENDPOINT_URL=http://localhost:4566` and dummy SDK credentials.
On AWS omit the endpoint override and use task-role credentials. Public API
startup does not require billing settings; the consumer fails startup without them.

From `services/scheduling`, start separate consumer and publisher processes:

```powershell
.venv/Scripts/python.exe -m app.payment_worker
.venv/Scripts/python.exe -m app.payment_worker --publish
```

Add `--once` to either command for one batch. The consumer polls for five seconds
to fit the shared SDK's ten-second read timeout. The separate publisher retries
pending outbox rows using M02 and does not wait for incoming payments.

## Verification

`tests/test_payments.py` exercises PostgreSQL transaction rollback, signed billing
adapter requests, mismatched IDs/amounts, replay with same or different event IDs,
concurrent confirmations, exact expiry and queue acknowledgement. Billing facts
and checkout state are labelled fixtures. Existing scheduling checks cover the
reservation constraint, expiry worker, access checks and cancellation locking.
Real billing/webhook/checkout and AWS integration remain unverified.

Local verification on 14 October 2026: all 201 scheduling tests passed on
PostgreSQL 17/Redis 7.4, including the opt-in live Floci payment EventBridge ->
SQS -> confirmation outbox -> EventBridge/SQS check. That check creates and
removes its own temporary bus, rules and queue; billing reads and checkout
state remain fixtures. Ruff lint/format, migration model parity, rollback/
re-upgrade and dependency checks passed.
