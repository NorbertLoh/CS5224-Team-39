# Stripe webhook inbox (B03)

B03 adds raw-body signature verification and durable event-ID deduplication to
the billing API. Payment transitions and transactional success events belong to
B04; accepting a receipt does not confirm a payment.

## Configure and run

Install the billing lockfile (including Stripe SDK 16.0.0), upgrade Alembic to
`head` (`0003`), and start the billing API as described in [CHECKOUT.md](CHECKOUT.md).
Set `SERVICE_STRIPE_WEBHOOK_SECRET` to this endpoint's `whsec_` signing secret.
It is separate from the API key and the unprefixed X04 spike variable. With no
signing secret or database, the receiver returns 503; existing checkout readiness
still checks checkout configuration independently.

The service-local route is `POST /webhooks/stripe`; external ingress stripping
the billing prefix exposes `POST /api/v1/billing/webhooks/stripe`. This route
authenticates through the signature and must be reachable without Cognito.
Shared ingress/Compose changes are outside B03. Do not cache or transform bodies.

For local forwarding through the Stripe CLI:

```text
stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,payment_intent.succeeded,payment_intent.payment_failed --forward-to http://localhost:8009/webhooks/stripe
```

Use the listener's signing secret for the local process; Dashboard and CLI
secrets differ. For a registered test endpoint select **Your account**, snapshot
payloads and API version `2024-06-20`, matching the checkout adapter. Use HTTPS
outside local development. Live events and thin payloads are rejected. These
choices follow [Stripe's webhook documentation](https://docs.stripe.com/webhooks).

## Receipt semantics

- The Stripe SDK verifies the exact request bytes and all `v1` signatures (allowing
  signing-key overlap). Exactly one `Stripe-Signature` header is required. The
  five-minute timestamp tolerance also rejects signatures too far in the future.
  The streamed body is limited to 256 KiB; keep the host clock synchronised.
- Valid snapshot envelopes are inserted into `billing.stripe_webhook_events`.
  The event-ID primary key and `INSERT ... ON CONFLICT DO NOTHING` handle retries
  and concurrent delivery across API instances. Duplicate deliveries verify their
  signatures again and never replace the first receipt or reset its status.
- 200 `{"received":true}` means a receipt committed or already exists. Signature,
  test-mode and envelope failures return 400; oversized bodies return 413;
  unavailable storage or commit failure returns 503 so Stripe can retry. Error
  responses/logs omit the payload, signature, SDK/SQL errors and signing secret.
- Checkout completion/expiry/async payment events and payment-intent success/failure
  enter as `pending`. Other event types enter as `ignored` and receive 200, so
  unrelated event subscriptions do not cause endless retries.
- Only provider event/account/version/time, bounded object references, amount,
  currency/status signals and `metadata.payment_id` are retained. Raw bodies,
  arbitrary metadata, customer details, addresses, card data and error text are
  discarded. Receipts are internal and have no patient-facing read API.

## B04 handoff and limits

No consumer runs in B03. Pending receipts must be drained independently of HTTP
delivery in B04; they are not marked processed on receipt. B04 must lock a receipt,
validate account, event/object type, trusted payment/session/intent linkage,
amount/currency and legal transitions, and save the payment, processed receipt
and outbox event in one transaction. It must handle separate event IDs describing
the same payment, out-of-order events, missing checkout linkage during concurrent
creation and late payment after hold expiry. Event-ID deduplication alone does
not make those business effects idempotent. Retrieve provider objects if the
minimal projection lacks required context; never infer success from the redirect.

Retain receipts while processing/reconciliation remains possible; no automatic
pruning is added here. An operator can inspect pending receipts with restricted
database access; do not manually mark them processed to bypass B04.

## Verification

Use the disposable PostgreSQL database/reset opt-in and commands in [README.md](README.md).
The suite covers raw-byte tampering, missing/duplicate/invalid headers, old/future
timestamps, signed malformed JSON/envelopes, live-mode rejection, size limits,
secret redaction, storage/commit failure and safe retry, process restart,
concurrent replay, projection privacy and ignored events. Existing checkout and
financial immutability checks run alongside migration upgrade/downgrade and
schema/ORM parity checks.

Local verification uses synthetic signatures and actual PostgreSQL. Real Stripe
delivery, payment-state transitions, scheduling confirmation and AWS ingress are
not established by these checks.

Observed on 18 October 2026: 167 billing tests plus 38 subtests passed locally
with PostgreSQL, along with Ruff lint/format and `pip check`. Migration round-trips
and Alembic schema parity passed. Actual loopback HTTP returned 200 for a signed
receipt and replay, 400 for body tampering, and left exactly one PostgreSQL
receipt. The existing Starlette TestClient deprecation warning remains.
