# B02 consultation checkout

The API implements C03's `POST /api/v1/billing/consultation-checkouts`.
Ingress must strip `/api/v1/billing`; the service-local route is
`POST /consultation-checkouts`. `root_path` supplies documentation/proxy metadata,
not an extra route prefix. Root proxy/Compose integration remains B07.

## Configuration and startup

Install the locked billing dependencies as described in README, migrate to `0002`,
and configure the `SERVICE_*` variables in `.env.example`. Existing unprefixed
`STRIPE_SECRET_KEY`/`STRIPE_CONNECTED_ACCOUNT_ID` configure only the X03 CLI;
the API uses `SERVICE_STRIPE_SECRET_KEY` and a JSON `SERVICE_STRIPE_DESTINATIONS`
map from clinic UUID to connected account ID. Only `sk_test_` keys are accepted.
There is no default clinic destination or successful provider fixture.

Set up these matching, distinct service credentials:

| Caller -> receiver | Caller setting | Receiver setting | Audience |
| --- | --- | --- | --- |
| billing -> scheduling | billing `SERVICE_SCHEDULING_SECRET` | scheduling `SERVICE_BILLING_SECRET` | `telelink-scheduling-billing` |
| scheduling -> billing | scheduling `SERVICE_BILLING_SECRET` | billing `SERVICE_SCHEDULING_SECRET` | `telelink-billing-scheduling` |
| billing -> tenant | billing `SERVICE_TENANT_SECRET` | tenant `SERVICE_BILLING_SECRET` | `telelink-tenant-billing` |

Configure scheduling's `SERVICE_BILLING_URL` to the billing service-local base
URL. Preserve scheduling's existing tenant booking/directory credentials.
Tenant's `SERVICE_BILLING_SECRET` is new and must differ from its other service
and cursor keys. Secrets require at least 32 bytes. JWT issuer/sub are the caller
service name; tokens last 60 seconds. User JWTs cannot access internal endpoints.
Public ingress must continue excluding `/internal/*`.

From `services/billing`, in separate terminals with the same environment:

```powershell
.venv/Scripts/python.exe -m app
.venv/Scripts/python.exe -m app.expire_checkouts
```

The expiry worker is required. `--once` performs one bounded pass for scheduled
or operator invocation. `/health/ready` checks DB migration, user authentication
and checkout configuration; it does not prove worker health or provider access.
Keep the worker supervised and monitor its pending count/errors.

Example request using a current owning-patient access token:

```http
POST /consultation-checkouts
Authorization: Bearer <patient-access-token>
Idempotency-Key: consultation-attempt-1
Content-Type: application/json

{"appointment_id":"<held-appointment-uuid>"}
```

Response is `{payment, checkout_url, expires_at}`, 201 for a new checkout and
200 for a successful replay. Patient/tenant/price/commission/return URLs are not
accepted in the body. Money is integer SGD; this card-only adapter accepts Stripe's
50 to 99,999,999 minor-unit range. Redirect URLs and CORS origins are configured
by the operator and require HTTPS outside local/test. Public payment fields omit
provider IDs, idempotency keys and Connect account IDs.

## Reservation and retries

Billing first durably allocates an attempt ID, then calls scheduling's
`POST /internal/appointments/{id}/checkout-reservation` with that payment ID and
the authenticated patient's server-resolved ID. Scheduling conceals foreign IDs,
checks clinic/doctor eligibility and uses its existing slot-first transaction
locks. It binds payment ID and `pending_payment` without renewing the original
deadline. A replacement payment requires independent proof that the bound prior
payment failed, through billing's scoped `GET /internal/payments/{id}`. This
minimal service read supports B02; public status/list APIs remain B05.

Billing reads commission from tenant's billing-only
`GET /internal/clinics/{id}/billing-profile`, calculates the rounded-down split,
and commits the B01 immutable payment snapshot plus exact provider parameters
before contacting Stripe. Destination charges retain the full application fee
and transfer destination in the persisted request. `provider_account_id` stays
null because the Checkout session/charge is owned by the platform; the connected
destination is in the stored provider parameters.

Request keys are scoped to patient and consultation checkout and retained
indefinitely (at least C03's 24 hours). A reused key for a different appointment
returns `idempotency_conflict`. Keys created while an attempt is pending alias the
same attempt; successful original requests replay their stored response even
after later payment/expiry changes. Check `expires_at` before using an old URL.
A fresh key after success returns `already_paid`. A definitive create rejection
records failure; a fresh key may retry before the original hold deadline.

Database advisory locks serialize by request key and appointment across API/worker
replicas, on a pinned connection across commits. Locks are released on completion
or connection/process loss. Bounded DB waits may return 503; retry the same key.

An uncertain provider result returns 503 `payment_pending_reconciliation` with
the stable payment UUID in `error.details` (`field=payment_id`). A new key cannot
create a different charge. Retry before hold expiry resumes the same persisted
Stripe key and parameters; after expiry the worker reconciles and expires that
same operation. Once an uncertain operation is 23 hours old, no create is retried:
Stripe may prune keys after 24 hours. Inspect the test Dashboard using the stored
payment metadata/provider key before an operator resolves it. Never mark failed
or clear an attempt merely because a timeout occurred. Public status retrieval
and authoritative success handling remain B03-B05.

## Approved Stripe expiry limitation

Stripe hosted Checkout accepts `expires_at` only 30 minutes to 24 hours after
creation, while C03's appointment hold is at most 10 minutes.
[Stripe create documentation](https://docs.stripe.com/api/checkout/sessions/create)
and [explicit expiry API](https://docs.stripe.com/api/checkout/sessions/expire).

On 18 October 2026 the requesting user approved keeping the original hold and
using an expiry worker. Stripe sessions receive a 35-minute provider deadline;
the public `expires_at` remains the original application hold deadline. The worker
polls every five seconds, reconciles lost responses with the original create key,
then retrieves/expires the provider session. Only a verified expired/unpaid session
can change a pending payment to failed. Complete sessions await B03/B04; expiry
cannot regress a concurrently recorded success.

This is best-effort provider expiry, not an atomic cutoff at the exact hold
instant. Worker/network outages or payment races can permit a late payment.
Scheduling's existing late-success/reallocated-slot/manual-refund policy remains
required. The worker does not confirm appointments, publish success events or
implement refunds. Scheduling's own expiry process continues releasing capacity.

## Verification

Use the disposable DB and explicit reset consent in README. Run `pytest -q`,
Ruff check/format, `pip check` and `alembic check`. Also run the scheduling and
tenant suites with their own restricted-role URLs and reset flags; scheduling's
complete suite requires Redis. The existing billing CI uses PostgreSQL 17.

Tests cover real PostgreSQL persistence/migration parity, user/service auth,
foreign ownership, strict request input, trusted upstream context, price and
commission snapshots, same/different-key concurrency, provider rejection,
uncertain replay with identical persisted parameters, provider response validation,
expiry reconciliation and retaining completed/succeeded payments.

This task does not establish webhook delivery, real payment success, frontend
checkout/return handling, Redis-backed booking creation, Cognito browser login,
AWS compatibility or the full consultation-payment journey.

Observed on 18 October 2026: a local HTTP walkthrough ran the actual identity,
tenant, scheduling and billing applications with restricted database roles on
disposable PostgreSQL 18, a synthetic local RSA issuer and a seeded synthetic
held appointment. Actual Stripe test-mode creation returned 201; replay returned
200 with the same response. SGD 50 total, SGD 5 commission, appointment/payment
linkage and the original deadline were verified. At that deadline the real
worker expired the unpaid Stripe session; an independent Stripe GET confirmed
`expired`/`unpaid`, and billing stored `failed`. No card payment was taken.

Merged PR #170 passed all twelve CI checks on PostgreSQL 17/Python 3.10:
billing 132 tests plus 38 subtests, scheduling with Redis 226 passed/two skipped,
and tenant 116 passed. Local checks also passed migration parity, Ruff and
`pip check`. After Docker became available, the full local scheduling suite with
isolated Redis 7.4 passed 226 tests with two skipped, matching CI and resolving
the earlier Redis-unavailable local test limitation. Issue #169 is closed.
