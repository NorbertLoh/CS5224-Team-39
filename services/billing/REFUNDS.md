# RF08 consultation refunds

Clinic admin: **Manage clinic → select clinic → Payments → Payment details → Refund payment**.
For a fresh refundable Stripe sandbox example, follow [the repeatable demo](../../docs/refund-demo.md).
Enter a reason, review the full amount and confirm. No platform approval is required.
The reason and requester name are visible in the payment's refund history; use a
short operational reason, not clinical notes.

Only current active clinic-admin membership for that payment's clinic grants
permission. Patient and platform-admin visibility does not grant refund authority.
Medicine/delivery payments have no refund action and are rejected by the backend.
Payment alone does not guarantee dispatch: paid-and-ready gating, expired quote,
changed fee, provider uncertainty and cancellation exceptions remain visible.

Public payment responses include `refund_availability`. Demo payment details show
that no actual charge was made and omit the refund form. Backend attempts against
these payments return `refund_demo_payment` before contacting scheduling or Stripe.
Only an actually active booking returns `refund_appointment_active`; other 409
responses use general unavailability guidance. The frontend preserves these safe
error codes rather than inferring cancellation requirements from HTTP status.

Cancel upcoming consultations in Appointments first. Completed, no-show, cancelled
and expired bookings may be reviewed for a full refund. Recorded duplicate/late
payment exceptions can be refunded without cancelling a different valid payment's
booking. A request never silently cancels an appointment.

## API and persistence

- `POST /payments/{payment_id}/refunds` with `{ "reason": "Patient cancellation" }`
  returns 202 and the durable operation. No client-supplied amount is accepted.
- `GET /payments/{payment_id}/refunds` returns audit history under the existing
  payment read policy (patient owner, own clinic admins, platform readers).
- Billing migration **0006** adds `refund_attempts`, request-audit protection and
  a unique active operation per payment. All financial amounts remain immutable.
- The existing `python -m app.payment_worker` processes refund requests as well as
  verified payment receipts. Its `--publish` process remains the outbox publisher.
  No new environment variables, queue or worker are needed.
- Apply `python -m alembic upgrade head` with the billing service environment and
  restart billing API/processor and scheduling API before using the UI. Billing
  readiness requires revision 0006. Never downgrade a database with refund history.

The scheduling review/completion endpoints accept only the existing billing service
credential. Review verifies terminal booking or a recorded payment exception;
completion independently reads the committed billing result before marking the
matching booking refunded. A different valid payment's booking remains untouched.
The scheduling exception resolver acknowledges pending, failed and completed
refunds without regressing their status or recreating review on a refunded payment.

## Provider behavior

Only actual Stripe **test-mode consultation payments** are supported, matching the
application's existing provider policy. Demo-seeded statuses/provider IDs cannot
issue refunds. Full refunds return the original paid amount; destination transfers
and any platform application fee are reversed. The original commission snapshot
remains historical; pending/failed/refunded payments are excluded from current
successful-payment commission totals.

The worker verifies the original PaymentIntent, amount, currency, metadata and
persisted destination/fee before creating a refund. Requests use a durable stable
Stripe idempotency key. Lost responses are reconciled by listing refunds before
replaying that same operation. After 23 hours an unknown operation is held for
support review rather than risking a newly created refund after key expiry.
Provider-pending outcomes are polled by ID; refund webhooks are not required.

The UI polls payment and refund state every five seconds. A provider success first
commits in billing; scheduling independently verifies it on a later worker pass.
Scheduling outages retry this synchronization without repeating the provider refund.
Only a provider-confirmed failed/cancelled refund allows an explicitly requested new
attempt, with a new audit entry/key. Rejections, unknown old operations, external
refunds and mismatched provider contexts require support review and cannot be
automatically retried. Partial or out-of-band refunds are not reconciled automatically.

Provider reference: [Stripe refunds API](https://docs.stripe.com/api/refunds/create)
and [destination charge refunds](https://docs.stripe.com/connect/destination-charges#issue-refunds).

## Verification

Use the isolated PostgreSQL setup in README; never run reset-enabled tests against
the demo database. Run billing pytest/Ruff/migration parity, scheduling refund and
checkout tests, frontend lint/typecheck/build. RF08 tests cover authorization and
revocation, medication exclusion, audit immutability, concurrent requests/workers,
lost responses, pending/failed refunds, explicit retries, provider-context mismatch,
external refunds, the idempotency cutoff and delayed scheduling synchronization.

Provider fixtures establish failure behavior, not actual Stripe integration.
Live verification evidence and limits are recorded in the PR.

Local verification on 23 October 2026: billing regression suite 306 passed plus
38 subtests; scheduling refund/checkout suite 17 passed; frontend lint and
typecheck/production build passed. One explicitly approved SGD 0.50 Stripe sandbox
PaymentIntent was fully refunded by the actual refund worker. Provider GETs
confirmed refund success, the full charge refund, destination transfer reversal
and SGD 0.05 application-fee refund. This used a disposable database and a scheduling
fixture; it does not establish a hosted Checkout → scheduling → refund journey.
Refunds omit `livemode` in Stripe responses; validation relies on the enforced
test-only key and linked test-mode PaymentIntent, rejecting explicit live markers.

The live seeded database was backed up before the additive migration, retained its
44 payments and has no new refund operations. All eight API readiness checks and
Tailscale billing readiness passed after the affected APIs/processor restarted.
AWS deployment and an actual multi-service refund journey remain unverified.
