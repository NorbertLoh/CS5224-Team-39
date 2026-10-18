# Payment processing and success publication (B04)

B04 drains verified Stripe receipts, commits validated payment transitions with
the receipt and C05 success event, and publishes the stored outbox through M02.
Payment status/list APIs and medication checkout remain B05/B06.

## Setup

Reinstall `requirements.lock.txt` and the editable billing package as described in
[README.md](README.md), then run `alembic upgrade head` (`0004`). Billing now needs
the shared AWS extra for publication; the lockfile includes its boto3 dependencies.
The API readiness check expects migration `0004`.

Keep the B02 expiry worker running. In separate terminals from `services/billing`:

```powershell
# Uses SERVICE_DATABASE_URL and SERVICE_STRIPE_SECRET_KEY (sk_test_ only).
.venv/Scripts/python.exe -m app.payment_worker

# Uses SERVICE_DATABASE_URL, SERVICE_EVENT_BUS_NAME and the shared AWS settings.
.venv/Scripts/python.exe -m app.payment_worker --publish
```

Both modes support `--once` for an operator/scheduled pass. The processing mode
prints processed/ignored/rejected/deferred counts in that mode. Database failures
roll back and retry continuously, or exit with status 1 under `--once`. A normal
pass can include deferred/rejected receipts: inspect its counts and stored codes.

For the normal offline stack, use `SERVICE_EVENT_BUS_NAME=telelink-local`,
`SERVICE_AWS_REGION=ap-southeast-1`, `SERVICE_AWS_ENDPOINT_URL=http://localhost:4566`
and synthetic `AWS_ACCESS_KEY_ID=test` / `AWS_SECRET_ACCESS_KEY=test`. Bootstrap the
C05 bus/consumer rules with the existing F12 scripts. In AWS omit the endpoint
override and dummy credentials; use the task role. No root Compose/ingress files
are changed here. The API and processor do not need EventBridge to accept/process
receipts; the separate publisher retries delivery while Stripe is unavailable.

## Processing rules

- The receiver still verifies raw signatures and commits receipts before HTTP
  acknowledgement; see [WEBHOOKS.md](WEBHOOKS.md). Workers claim due pending rows
  with `FOR UPDATE SKIP LOCKED`, then acquire the same appointment advisory lock
  used by checkout/expiry and lock the payment. An in-flight checkout defers the
  receipt instead of racing provider linkage or creating another charge.
- B04 makes only authenticated Stripe GET requests using the existing pinned API
  version. It matches the receipt account/object/session/intent and optional amount
  fields, retrieves the stored session and its PaymentIntent, and validates the
  test-mode provider response, original payment/appointment/tenant/patient/purpose
  metadata, amount/currency, destination and commission. Destination comes from
  persisted B02 provider parameters, so later clinic configuration changes cannot
  redirect old payments. A partial transfer is rejected.
- A complete paid session requires a succeeded PaymentIntent for the exact received
  amount. `pending` or `failed` becomes `succeeded` once; an immutable C05
  `consultation_payment_succeeded.v1` envelope is staged in the same transaction
  as the payment, checkout closure and processed receipt. Event and correlation
  IDs are stable per payment. Separate provider event IDs for one payment produce
  one success; later failures never regress succeeded/refund states.
- Confirmed expired/unpaid sessions and terminal asynchronous session failures
  can fail a pending payment. A card decline in an open session keeps the payment
  pending because the patient can retry that session. Provider `processing` and
  incomplete success linkage retry with backoff. Nonterminal verified receipts
  may finish without changing payment state; the next terminal event establishes
  the outcome. Periodic scanning of all provider sessions is outside this task.
- A late success is still a paid fact and is published even after local expiry.
  Scheduling consumes the success, verifies the bound payment and owns slot
  recovery, duplicate-charge and refund-required decisions. Billing never confirms
  an appointment through cross-service database writes.
- Timeout/unavailable provider data and unfinished checkout linkage retain the
  receipt as pending, with safe error codes, attempt count and retry time (5s
  exponential backoff capped at five minutes). Bad linkage/amount/account or an
  integrity conflict becomes rejected for operator review. Other account events
  without application linkage are ignored. No raw provider error text is stored.
- The publisher uses M02's stored envelope, row locking, publication tracking and
  per-entry retry. Transport is at least once: a crash after provider acceptance
  but before publication commit may resend the same event ID; consumers must use
  their M03 inbox. Publication failure never reverses committed payment truth.

## Operator review and limits

Inspect pending/rejected receipts through restricted database access, especially
`last_error`, `attempts` and `next_attempt_at`. Deferred `checkout_linkage_pending`
needs the B02 same-key checkout retry or expiry reconciliation to recover the lost
session reference; B04 does not recreate the provider operation. Rejected receipts
do not retry automatically. After investigating and correcting trusted linkage or
configuration, an operator may reset the specific receipt to pending and set
`next_attempt_at=now()`; preserve its ID/projection and audit the intervention.
Do not mark it processed or edit financial snapshots to hide a mismatch.

B04 currently processes the B02 consultation checkout shape. B06 must extend the
trusted order/quote checkout context and medication success projection. No refund
operation or new payment status/list API is added. The existing scheduling
refund-resolution handoff still needs a billing receiver; record that as integration
follow-up rather than treating this worker as full late-payment/refund integration.
Frontend booking/payment journeys and real AWS ingress/delivery remain unverified.

## Verification

Use only the disposable database and reset opt-in from [README.md](README.md),
then run its billing pytest, Ruff and `pip check` commands. Focused cases cover
signed receipt ingestion, atomic commit/rollback, competing receipts/workers,
late success, terminal expiry versus retryable decline, trusted provider context,
conflicting intent ownership, durable retry and publication with an unchanged
event ID. Migration checks cover schema parity and upgrade/downgrade isolation.

Local provider responses/signatures are synthetic unless explicitly stated;
these checks do not establish a real Stripe callback or payment.

Observed on 18 October 2026: 201 billing tests plus 38 subtests passed against
disposable PostgreSQL, with Ruff lint/format and `pip check` passing. An actual
loopback HTTP signed callback/replay plus a separate success receipt produced one
payment/outbox success, then the real SDK published through isolated Floci 2.2.0
EventBridge to one SQS C05 message; a second publisher pass sent nothing. Stripe
reads were simulated in this transport check. The existing Starlette TestClient
deprecation warning remains.
