# Medication payment consumer (D04)

The separate worker consumes the C05 `medication_payment_succeeded.v1` event from
the fulfilment SQS queue. It uses M03 to commit the fulfilment-owned inbox row and
the order's paid state in one PostgreSQL transaction. It never submits delivery.

## Setup

Install the updated `requirements.lock.txt` (including the AWS SDK), then run
`python -m alembic upgrade head` as the restricted fulfilment database role before
starting the API or worker. Migration `0003` creates `fulfilment.event_inbox`;
readiness checks require it. No other service's tables or schema are changed.

Set the usual `SERVICE_DATABASE_URL` and these worker settings:

| Setting | Value |
| --- | --- |
| `SERVICE_BILLING_URL` | Billing service root; e.g. `http://localhost:8009` locally; HTTPS outside local/test |
| `SERVICE_BILLING_SECRET` | Private, at least 32 bytes, distinct from the cursor secret; matches billing's `SERVICE_FULFILMENT_SECRET` |
| `SERVICE_PAYMENT_QUEUE_NAME` | Defaults to `telelink-local-fulfilment`; queue must already exist |
| `SERVICE_AWS_REGION` | Defaults to `ap-southeast-1` |
| `SERVICE_AWS_ENDPOINT_URL` | `http://localhost:4566` on the host or `http://floci:4566` in Compose; local/test only |

Use dummy `AWS_ACCESS_KEY_ID=test` and `AWS_SECRET_ACCESS_KEY=test` for Floci. On AWS,
omit the endpoint override and use the worker's scoped task-role credentials. F12's
existing routing matches source `telelink.billing` and the exact medication event
type, delivering the full EventBridge wrapper to this queue. Retain its bounded
retry/DLQ configuration. No shared Compose, routing or infrastructure change is
included in D04; launch the worker separately:

```powershell
python -m app.payment_worker --once
python -m app.payment_worker
```

The first command handles one batch and reports processed/duplicate/failed counts;
the second polls continuously. Five-second long polling stays within the SDK's
ten-second read timeout. Stop the process normally when finished.

## Validation and state changes

The worker retrieves `GET /internal/payments/{payment_id}` from billing using a
60-second HS256 service token: issuer `telelink-service:fulfilment`, subject
`fulfilment`, audience `telelink-billing-fulfilment`. Browser credentials are never
forwarded. Redirects, failed HTTP responses, invalid JSON and incomplete payment
responses fail closed. Billing separately restricts this caller to medication
payments.

Before applying a payment, D04 locks the order row and verifies all of:

- Event source/type/version and IDs through the shared C05 parser.
- Billing payment ID, order, tenant, patient, purpose `medication_delivery`, status
  `succeeded` and resolution `none`.
- Event tenant and exact amount against billing and the reserved order; SGD only.
- The order's reserved payment ID and quote ID, an `accepted` quote belonging to
  that order/tenant, and matching medication subtotal, delivery fee and total.

Only an `awaiting_payment` order with `payment_status=pending` can first transition
to `status=paid`, `payment_status=succeeded`, with a server UTC `updated_at`.
Readiness, quote, amounts, payment ID and delivery ID remain unchanged. An accepted
quote may have expired by consumption time: that does not erase a valid payment;
D05 must revalidate delivery pricing before submission.

Duplicate event IDs skip the handler after the committed inbox lookup. A new event
ID for the same verified payment is also safe: an already-succeeded order retains
its state and timestamp, including later delivery states. The order lock serializes
concurrent handlers and shares the locking convention used by readiness and quotes.

The consumer deletes SQS messages only after commit. A failed commit or validation
leaves both order and inbox unchanged, and leaves the message unacknowledged. A
failed delete after commit is safe on redelivery. Concurrent inserts of the same
inbox key may fail once and deduplicate on retry, as defined by M03.

## Recovery and integration limits

Missing reservations, cancelled orders, refund states, different payment IDs,
conflicting facts and unavailable billing reads remain retryable and eventually
reach the configured consumer DLQ. Correct the upstream/configuration problem or
resolve the payment manually before replaying with the same event ID. Do not
delete an inbox entry to force a transition. See the shared
[DLQ/replay procedure](../../docs/messaging-replay.md). Automatic refund/reconciliation
and delivery submission are outside D04.

The fulfilment `/internal/orders/{id}/checkout-reservation` endpoint used by B06 is
still unfinished. D04 requires its intended persisted state: the order references
the payment and accepted quote and has pending payment status. It fails closed
when that state is absent. Unit and local transport checks explicitly seed
synthetic reservations and succeeded billing payments; they do not establish a
Stripe transaction or complete I03. Real dispensing integration also remains open.

## Verification

The fulfilment PostgreSQL suite covers migration round trips/drift, scoped billing
JWT claims, tenant/patient/payment/quote/purpose/amount mismatches, invalid events,
ready-first and payment-first outcomes, both duplicate forms, six concurrent
requests, rollback after flushed state and inbox, acknowledgement failure, and
preservation of delivery state. Run the suite and Ruff using [README.md](README.md).

On 19 October 2026, local verification passed 206 PostgreSQL/API tests and Ruff.
A separate loopback check used the actual billing API and isolated Floci 2.2.0 SQS
on a dedicated queue. Separate `--once` worker processes verified both readiness
orders, duplicate event redelivery and new-event-ID payment replay without changing
the committed timestamp or starting delivery. A different-tenant message failed
without an inbox commit. Unauthenticated billing reads returned 401 and the protected
database sentinel survived. Billing payments and accepted reservations were operator
fixtures; AWS, real Stripe and the full checkout/reservation journey were not tested.
