# B06 medication and delivery checkout

Implements the billing side of C04, tracked by issue #181 / PR #182.
D07 implements the real fulfilment reservation adapter and connects the local
paid-and-ready sandbox journey. See [D07 setup and evidence](../../docs/D07-live-fulfilment.md).
B06 unit/service tests use explicit C04 and Stripe fixtures; actual doctor issuance,
physical delivery and deployed AWS integration remain separate I03 work.

## Public checkout

`POST /api/v1/billing/medication-checkouts` (service-local `/medication-checkouts`)
requires a current authenticated patient and C03 `Idempotency-Key`. Body accepts
only `order_id` and `quote_id` UUIDs. Returns `{payment, checkout_url, expires_at}`,
201 on creation, 200 on replay. Browser totals, quantities, tenant/patient/provider
IDs and return URLs are rejected. The public payment purpose is
`medication_delivery`, with null appointment and nonnull order/quote IDs.

Billing obtains an atomic trusted fulfilment reservation, validates response
ownership/operation links, accepted/pending states, timezone-aware future expiry,
unique prescription item IDs, positive integer quantities, each line's arithmetic,
subtotal and total in SGD. It then fetches the active tenant billing profile.
The original reservation is persisted; a changed accepted snapshot cannot resume
an uncertain provider operation. Commission is rounded down on medication subtotal
only; the clinic gross amount includes delivery. No addresses or clinical text
are stored in this checkout projection.

Same subject/key with different order/quote gives 409 `idempotency_conflict`.
New keys for the same pending order/quote return the current operation; different
quotes are blocked while it is pending. PostgreSQL advisory locks and a unique
open-order index serialize competing attempts. The payment UUID is durable before
reservation, and money/exact provider fields are durable before Stripe creation.
Timeouts keep the same operation/provider idempotency key; never infer failure or
create a new charge after uncertainty. Stripe retry age remains limited to 23 hours.
An original completed request replays its original response, including after expiry;
use the payment status API for current state. A succeeded/refund-state payment
blocks creation with new keys. Failed attempts remain historical; fulfilment must
reconcile the prior failure before releasing acceptance for a new attempt.

## Trusted fulfilment adapter boundary

Set `SERVICE_FULFILMENT_URL` to the service base URL (without `/api/v1/fulfilment`
when calling service-local routes) and independent `SERVICE_FULFILMENT_SECRET`
(at least 32 bytes). Both are required by full API readiness. Match the credential
on the fulfilment adapter. Keep it distinct from scheduling/tenant keys.
There is no implicit fixture mode or fallback to browser pricing.

Billing sends POST `/internal/orders/{order_id}/checkout-reservation` with
`{quote_id, patient_id, payment_id}`. The patient is the verified identity subject,
not a browser field. Authentication is a 60-second HS256 service JWT:
issuer `telelink-service:billing`, subject `billing`, audience
`telelink-fulfilment-billing`, signed by the fulfilment secret. Request IDs propagate.
The D07 adapter enforces the C04 atomic reservation checks, including issued
prescription quantities, order/quote tenant and patient ownership, exact quote
expiry, one accepted attempt and frozen pricing. Billing additionally validates the returned minimum projection; clinical-record
access and atomic quote ownership remain fulfilment-owned responsibilities.

The 200 response projection used by this adapter is:

```json
{
  "order_id": "<order UUID>",
  "quote_id": "<quote UUID>",
  "tenant_id": "<clinic UUID>",
  "patient_id": "<verified patient UUID>",
  "payment_id": "<billing operation UUID>",
  "status": "awaiting_payment",
  "payment_status": "pending",
  "quote_status": "accepted",
  "items": [
    {
      "prescription_item_id": "<issued item UUID>",
      "medication_id": "<catalogue UUID>",
      "quantity": 2,
      "unit_price": { "amount_minor": 1000, "currency": "SGD" },
      "line_total": { "amount_minor": 2000, "currency": "SGD" }
    }
  ],
  "medication_subtotal": { "amount_minor": 2000, "currency": "SGD" },
  "delivery_fee": { "amount_minor": 500, "currency": "SGD" },
  "total": { "amount_minor": 2500, "currency": "SGD" },
  "expires_at": "<original quote deadline with timezone>"
}
```

Display names, addresses, provider references and clinical instructions are not
required by billing and are dropped from the stored projection. Unknown/foreign
orders use concealed 404; known conflicts use C04 409 codes. Invalid upstream
data gives 502; unavailable/unconfigured sources give 503. An uncertain reservation
is retried using the same persisted payment identity. Failed profile/configuration
after a reservation leaves that identity available for recovery; do not release
or re-quote an uncertain accepted order based solely on an HTTP error.

## Expiry and payment truth

On 18 October 2026 the requester approved B02's prototype expiry exception for B06.
Hosted Stripe Checkout has a [30-minute minimum session lifetime](https://docs.stripe.com/api/checkout/sessions/create#checkout_session_create-expires_at),
which cannot guarantee C04's at-most-10-minute quote deadline. The returned
application deadline stays equal to quote expiry. Stripe gets the same 35-minute
session window as B02. Run the required worker every five seconds:

```powershell
python -m alembic upgrade head
python -m app
```

In separate processes with the same billing/provider configuration:

```powershell
python -m app.expire_checkouts
python -m app.payment_worker
python -m app.payment_worker --publish
```

See [CHECKOUT.md](CHECKOUT.md) and [PAYMENT_PROCESSING.md](PAYMENT_PROCESSING.md)
for provider credentials, worker options and event-bus setup. Migration head is
`0005`; it adds only billing-owned medication attempt/key tables.

The reservation and its original deadline are durable before tenant/profile calls.
For an expired reservation without a Payment row, the expiry worker closes the
operation under its advisory lock; no Stripe create has begun. Fulfilment can read
`GET /internal/medication-checkouts/{payment_id}` with its service JWT to verify
exact operation context and terminal failure before releasing acceptance. The
public patient reconciliation route is documented in the D07 setup. Pending,
unknown and successful outcomes never release the binding.

Expiry reconciles a lost create response using the original Stripe key, then
expires/reads the provider session. Only verified expired/unpaid becomes failed;
paid/uncertain outcomes are preserved. An unavailable worker/provider can leave
the payment page open beyond quote expiry. This is best effort, not a guaranteed
provider deadline. API requests crossing expiry never return a new usable checkout.

Raw signed webhooks go through B03/B04's durable inbox, provider reconciliation,
transactional payment update and outbox. Metadata must match payment, tenant,
patient, purpose, order and quote; amount/currency/destination/commission are checked.
Successful payment produces exactly one C05 `medication_payment_succeeded.v1`
containing payment ID, order ID and total SGD amount. It is a payment fact, not
permission to dispatch. If first success processing occurs at/after quote expiry,
billing conservatively sets `resolution=refund_required`, recording reason and
time. This also flags timely payments whose processing was delayed. No automatic
refund or delivery is implemented. Duplicate success preserves existing state.

Fulfilment must fetch `/internal/payments/{payment_id}` with its service JWT
(issuer `telelink-service:fulfilment`, subject `fulfilment`, audience
`telelink-billing-fulfilment`, same fulfilment secret). Only medication payments
are visible to this caller; scheduling credentials see only consultation payments.
Before marking paid/dispatching, verify exact bound IDs/amount and `resolution=none`,
then apply C04's late/cancelled/superseded quote and paid-AND-ready gates. D04-D07
implement those fulfilment decisions, including fee revalidation after readiness.

Fulfilment may POST `/internal/payments/{payment_id}/resolution` with
`{"resolution":"refund_required","resource_id":"<order UUID>","reason":"quote_expired"}`.
Other allowed reasons: `order_cancelled`, `delivery_price_changed`, `duplicate_charge`.
It validates purpose, linked order, stored reservation tenant and committed success
(including refund_pending/refund_failed). Repeats are idempotent and retain the
first recorded reason/time. This only flags manual review; it never calls Stripe
refund. Scheduling resolution and actual operator refunds remain separate work.
Exclude all `/internal/*` routes from public ingress.

## Verification

Run the disposable PostgreSQL suite and Ruff as described in [README.md](README.md).
On 18 October 2026, 285 billing tests plus 38 subtests passed on disposable
PostgreSQL 18, alongside Ruff lint/format and `pip check`. Actual loopback HTTP
also passed patient auth, checkout/replay, tampering/concealment, medication
success/outbox and fulfilment read/resolution with explicitly synthetic upstream
transports. These were fixture checks. D07 separately verified actual sandbox Stripe payment,
signed receipts, local event consumption and Lalamove submission/tracking; see
the linked evidence for limits and current suite totals.

The B06 tests cover trusted totals/line arithmetic, ownership and role checks,
tampering, expiry equality, concurrent requests, durable reservation/provider
retry, frozen snapshots, expiry versus paid state, signed medication events,
metadata mismatches, transaction rollback and fulfilment-only resolution.
