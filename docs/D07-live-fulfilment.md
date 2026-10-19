# D07 live fulfilment

Tracked by issue #223 and PR #224. Patient medication ordering and clinic readiness
now call authenticated service APIs. Preview routes remain explicitly synthetic.

## Pages and behaviour

- `/patient/medication-orders`: own orders, current server quote, separate medication
  Stripe Checkout, payment confirmation and delivery tracking.
- An issued patient prescription links to the ordering page. Creating/opening its
  order sends only the prescription ID; quantities come from clinical records.
- `/clinic-admin/clinics/<tenant UUID>/orders`: active owning-clinic admins can read
  orders and mark medicine ready. A platform role alone cannot open this page.

Lists use API cursors and refresh every ten seconds; selected orders refresh every
five seconds. Linked payment and delivery reads must match the current order,
patient and clinic. Errors never substitute demo data. Order border colours and
text distinguish attention, waiting, progress, delivered and refunded states.
Selection retains the status border. Payment success and medicine readiness are
separate facts; a successful browser return parameter cannot mark an order paid.

The browser retains subject/order/quote-scoped operation keys in session storage,
including after timeouts and reloads. It does not store delivery addresses there.
Changed addresses require a new server quote. Checkout retry uses the same key
until authoritative failure is observed. Return URLs restore the selected order;
the current authenticated subject and API response still determine access.

## Services and configuration

Apply existing migrations: clinical-records' current head, fulfilment `0005`, and
billing `0005`. D07 introduces no migration, root Compose or infrastructure change.
Configure the current Cognito issuer/JWKS/client and identity URL for all APIs.
Use independent random service secrets of at least 32 bytes:

| Caller and peer       | Settings to match                                                        |
| --------------------- | ------------------------------------------------------------------------ |
| Fulfilment → records  | fulfilment `SERVICE_RECORDS_SECRET`; records `SERVICE_FULFILMENT_SECRET` |
| Billing ↔ fulfilment | billing `SERVICE_FULFILMENT_SECRET`; fulfilment `SERVICE_BILLING_SECRET` |

Set fulfilment `SERVICE_RECORDS_URL=http://localhost:8005/api/v1/clinical-records`.
Records routes include that prefix. Direct fulfilment/billing base URLs omit their
ingress prefixes: billing `SERVICE_FULFILMENT_URL=http://localhost:8006`, fulfilment
`SERVICE_BILLING_URL=http://localhost:8009`. Do not enable
`SERVICE_DISPENSING_FIXTURE_PATH` alongside the records URL. Missing configuration
or an unavailable source fails closed; there is no automatic fixture fallback.

Configure actual sandbox Lalamove credentials, private origin/postcode coordinate
and contact directories as described in [QUOTES.md](../services/fulfilment/QUOTES.md)
and [DELIVERIES.md](../services/fulfilment/DELIVERIES.md). Supported destination
postcodes must have trusted coordinates. Configure billing's Stripe test API key,
connected-account mapping, tenant billing-profile secret and signed webhook
endpoint as described in [MEDICATION_CHECKOUT.md](../services/billing/MEDICATION_CHECKOUT.md).
No provider credentials belong in frontend environment variables.

Medication return URLs default to the configured consultation return origin at
`/patient/medication-orders`; billing appends its own `order_id`. Optional
`SERVICE_MEDICATION_CHECKOUT_SUCCESS_URL` and
`SERVICE_MEDICATION_CHECKOUT_CANCEL_URL` override the medication route. Local
authentication and Stripe return URLs should consistently use `localhost:5173`.

Run each API with `python -m app` from its service directory. In separate processes
with the same service configuration, run:

| Service directory | Command                                   |
| ----------------- | ----------------------------------------- |
| billing           | `python -m app.expire_checkouts`          |
| billing           | `python -m app.payment_worker`            |
| billing           | `python -m app.payment_worker --publish`  |
| fulfilment        | `python -m app.payment_worker`            |
| fulfilment        | `python -m app.delivery_worker`           |
| fulfilment        | `python -m app.delivery_worker --resolve` |
| fulfilment        | `python -m app.delivery_worker --publish` |
| fulfilment        | `python -m app.tracking_worker`           |

Configure the C05 EventBridge rule/SQS queue and worker credentials using
[PAYMENTS.md](../services/fulfilment/PAYMENTS.md). Run one tracking poller per provider
account. A payment webhook forwarder is required locally. APIs alone do not process
payment events, submit deliveries or refresh provider status.

## Trusted boundaries and recovery

Records exposes service-only GET
`/api/v1/clinical-records/internal/prescriptions/{id}/dispensing`, with explicit
`patient_id` and `purpose=dispensing`. A short-lived fulfilment JWT uses audience
`telelink-records-fulfilment`. Only issued, correctly linked prescriptions return
item/medication IDs and quantities. The read is audited before responding and
contains no clinical instructions. Public ingress must exclude internal routes.

Fulfilment's service-only POST `/internal/orders/{id}/checkout-reservation` locks
the order, checks the current quote and issued dispensing quantities, freezes the
server amounts and binds the billing operation. Retries keep the accepted snapshot.
No browser-supplied prices, payment ownership or service credentials are accepted.

An uncertain request must retain its key and binding. Fulfilment can release an
old attempt only after billing's service-only
`GET /internal/medication-checkouts/{payment_id}` confirms terminal failure with
exact payment/order/quote/patient linkage. Unknown, pending and successful outcomes
block replacement. Billing persists the reservation deadline before subsequent
upstream calls. Its expiry worker can close a reservation with no payment row
under the checkout operation lock, since Stripe creation has not begun.

The patient's **Recheck expired payment** invokes authenticated
`POST /orders/{id}/reconcile-payment` with an empty body. It applies the same
authoritative-failure check, including an expired reservation without a payment
row. A cleared/expired quote can then be replaced. This endpoint never changes
Stripe state or treats a timeout as failure.

The existing prototype expiry exception still applies: Stripe's hosted session
lifetime exceeds the short application quote deadline. Keep the expiry worker
running. Late/uncertain payments require reconciliation and may require manual
refund review. There is no automatic refund, guaranteed provider deadline or
automatic replacement of an uncertain delivery.

## Verification on 19 October 2026

Disposable PostgreSQL suites passed: fulfilment 315 tests plus four additional patient-reconciliation cases; clinical records 135;
billing 287 plus 38 subtests. Frontend passed 137 tests, ESLint, TypeScript and
production build; touched files were formatted with Prettier and Python with Ruff.

Actual local PKCE sessions, current identity and an existing confirmed consultation
were used with separate records/fulfilment/billing schemas. The starting issued
prescription was operator-seeded synthetic test data. Subsequent reads, audited
dispensing, catalogue/order creation, Lalamove quote, clinic readiness and patient
checkout used actual APIs without HTTP mocks. Desktop/mobile browser journeys
passed without runtime errors or horizontal overflow.

The user completed the real hosted Stripe **sandbox** checkout for SGD 27.80
(SGD 20 medication plus SGD 7.80 delivery). Two genuine signed webhook receipts
were processed; billing became succeeded and the payment outbox/isolated local
EventBridge/SQS consumer made fulfilment paid. The real ready-and-paid worker
revalidated the fee and created one Lalamove sandbox order. That synthetic courier
order was cancelled for cleanup; an actual provider GET and tracking worker
persisted cancelled/exception while preserving succeeded payment.

This establishes the scoped local/sandbox D07 integration. It does not establish
actual doctor issuance, physical pickup/completion, deployed AWS behaviour or the
full I02/I03 journey. The local cancelled sandbox example intentionally shows a
delivery problem, not a delivered order or refunded payment.
