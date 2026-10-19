# Verified delivery polling (D06)

D06 uses authenticated provider polling to update the fulfilment delivery and its
owning order. It reuses D05's sandbox HMAC adapter and immutable submission context.
It does not register a webhook, accept callback bodies, create provider orders, or
retry uncertain order submissions.

## Setup and operation

Run `python -m alembic upgrade head` with the restricted fulfilment database role
before starting the updated API or poller. Migration `0005` adds durable poll
scheduling, last successful observation time, failure count and a safe error code.
Existing deliveries receive defaults without changing their status. Readiness
checks require the migrated polling column.

Configure `SERVICE_DATABASE_URL`, `SERVICE_LALAMOVE_API_KEY` and
`SERVICE_LALAMOVE_API_SECRET` as for D05. Only the fixed SG sandbox endpoint and
test-prefixed provider credentials are supported. Tracking does not need contacts,
the location directory, billing credentials or a browser token. Run separately from
the API, submission worker and outbox publisher:

```powershell
python -m app.tracking_worker --once
python -m app.tracking_worker
```

`--once` polls at most one due delivery and reports `updated`, `unchanged`, `failed`,
`skipped` or `idle`. Continuous mode waits two seconds between requests, including
empty ticks. `SERVICE_DELIVERY_POLL_INTERVAL_SECONDS` defaults to 60, with a range
of 30–3600 seconds per delivery. Run **one poller per provider account**. Its maximum
rate is 30 GETs/minute, leaving headroom under the documented sandbox limit of 50;
other account clients also share that quota. See the provider's
[API reference](https://developers.lalamove.com/#errors). A backlog can make an
individual delivery's observed update later than its configured interval.

Due times are stored in PostgreSQL, so a process restart cannot discard the wait.
Failures back off exponentially from twice the configured interval, capped at one
hour. Successful verified observations reset the failure count. HTTP errors,
timeouts, redirects, unknown statuses and mismatched context retain the last
application status and stage no status event. `poll_error` stores only
`provider_verification_unavailable`; raw provider bodies and contacts are not
persisted in polling diagnostics.

Terminal delivered/cancelled/failed rows are no longer polled. Unknown submissions
with a stored provider reference can recover through the same independent verified
GET. Unknown submissions without a reference stay with the D05 operator procedure;
polling cannot infer an order ID or resubmit it. A failed observation is a poll
failure, not evidence of a failed delivery. `last_polled_at` records successful
verified observations, and the poll fields are private operational metadata.

## Verification and state mapping

The worker retrieves only `GET /v3/orders/{stored_provider_id}` over authenticated
HTTPS. It verifies the reference, local delivery/operation metadata, fresh provider
quote ID, frozen addresses/coordinates and exact SGD fee through D05's adapter.
Local order/delivery/quote ownership and submission intent must also match. A
valid HTTP response alone is insufficient to update state.

| Verified provider status | Normalized result |
| --- | --- |
| `ASSIGNING_DRIVER`, `ON_GOING` | submitted; never regress an existing picked_up state |
| `PICKED_UP` | picked_up |
| `COMPLETED` | delivered, including a jump over missed intermediate observations |
| `CANCELED` | cancelled from submitted; failed from picked_up or uncertain acceptance |
| `REJECTED`, `EXPIRED` | failed |

The provider can reassign a driver after progress; the application keeps its
pickup high-water state until a verified completion or failure. Delivered remains
terminal. Failed/cancelled records require operator resolution rather than being
automatically revived from a contradictory observation.

Order state becomes dispatched for accepted/picked-up deliveries, delivered on
completion, and exception for cancellation/failure. Payment ID, paid amounts and
payment status remain unchanged. A provider cancellation does not prove a refund;
payment/refund review stays explicit. This does not implement the patient/clinic
application cancellation endpoint or automatic refunds.

The order and delivery locks are held through GET and commit, using D05's order-first
lock convention. Concurrent pollers recheck due time and terminal state under lock.
An observation cannot overwrite a newer committed state. Duplicate or regressive
snapshots update only successful poll scheduling, preserving public timestamps and
staging no duplicate event. A real state change atomically updates the order,
delivery and C05 `delivery_status_changed.v1` outbox entry. The event contains only
operational IDs/status. Rollback also rolls back its schedule, so retry is safe.
Run D05's `python -m app.delivery_worker --publish` separately to publish events.

## Evidence and limits

The local PostgreSQL suite passed 304 tests on 19 October 2026, including migrations,
all supported mappings, missed-state completion, duplicate snapshots, pickup
regression rejection, delivered/failed/cancelled terminals, six concurrent pollers,
durable scheduling/backoff/restart, invalid local linkage, actual-adapter reference/
metadata/quote/fee/route rejection, HTTP/timeout failures, transaction rollback and
minimal event contents. Ruff lint and formatting also passed.

The actual SG sandbox check used provider order `3609208707651130210`. An initial
authenticated poll verified the unchanged accepted state. A restarted worker was
idle because its 30-second test interval was stored in the database. After the
fixture was cancelled and a separate provider GET verified `CANCELED`, the next
scheduled worker poll persisted delivery `cancelled`, order `exception`, and one
cancelled outbox event. Its paid amount/status stayed unchanged. A further worker
run was idle on the terminal delivery. The sandbox fixture is cancelled; no
callback was registered or sent to the application.

Pickup and completed states use controlled provider responses. Real physical
pickup/completion, AWS deployment, real dispensing/checkout reservations and the
full Stripe medication journey remain unverified. The actual sandbox polling
check uses synthetic landmark stops, contacts, accepted reservation and payment
facts; it does not represent a real patient shipment or Stripe charge.

Use the disposable database/test setup in [README.md](README.md). No shared root
Compose, contract, frontend, ingress or provider webhook configuration is changed.
