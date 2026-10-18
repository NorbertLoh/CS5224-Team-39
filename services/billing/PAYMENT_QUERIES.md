# B05 payment queries

All routes below are service-local; ingress strips `/api/v1/billing` as in C01.
They require a verified access token and a fresh identity-service lookup on every
request. Patient role grants access to the caller's own payments across clinics;
active clinic-admin memberships grant access to payments in those clinics.
These grants combine for callers with both roles. Platform admins see all
payments. Doctors have no independent billing access. No role/tenant from the
browser or pagination cursor grants access.

| GET route | Result / filters |
| --- | --- |
| `/payments/{payment_id}` | C03 public payment including status and resolution; inaccessible or absent IDs return the same 404 |
| `/payments` | C01 `{items, next_cursor}`; optional `tenant_id`, `purpose`, `status`; `limit` defaults to 25 (1–100), optional `cursor` |
| `/commission-totals` | Admin-only `{payment_count, amount, commission_amount, clinic_amount}`; optional `tenant_id`, `purpose` |

List order is `created_at, payment_id` ascending, with keyset pagination. Cursors
expire after 15 minutes and bind the caller, current access scope, ordering and
all filters. Changed filters, caller or permissions require restarting pagination;
invalid, expired or tampered cursors return 422 with `query.cursor` detail. Access
is checked again on every page. A selected tenant only narrows authorised rows;
foreign tenants return an empty list/zero totals. No snapshot consistency across
pages is promised. A caller without any permitted role gets 403 for collections
and totals; a payment detail remains concealed with 404.

Detail/list responses reuse the public C03 projection; they contain no provider
references, checkout URLs, webhook data or clinical content. All responses have
`Cache-Control: no-store`. Reads do not contact Stripe, change payment truth or
confirm appointments. The existing scheduling-only internal read is unchanged.

Totals allow active clinic admins over their clinics and platform admins over
all clinics. Patient ownership does not grant totals access or widen an admin's
totals scope. They include only `status=succeeded` and `resolution=none`, across
all dates, summing immutable stored amounts and commission snapshots separately
per payment attempt. Pending, failed, refund-required, refund-pending,
refund-failed and refunded payments are excluded. No current clinic commission
rate is used, and delivery fees are excluded from commission by the original
snapshot. `clinic_amount` includes delivery cost; it is the gross non-platform
portion. These are operational current-state totals, not net Stripe settlement,
accounting revenue or a refund ledger. A duplicate charge stays included until
marked for refund; B05 does not establish scheduling/refund integration.

Every amount is C01 SGD Money. Empty totals are zero. If an aggregate exceeds
the JavaScript safe integer range, return 409 `totals_limit_exceeded`; narrow by
tenant/purpose. No floating-point conversion, truncation or silent overflow.

## Configuration and verification

Set `SERVICE_CURSOR_SECRET` to an independent random secret of at least 32 bytes
(synthetic local example in `.env.example`). Keep it stable across billing API
replicas; rotation invalidates existing cursors. Without it, the payment list
returns 503 and readiness fails. Detail and totals need database/auth/identity
configuration; they do not require a Stripe call. No migration is added; run
the existing migrations through `0004` and start the API as in `CHECKOUT.md`.

Example requests, with an existing access token in `$billingAccessToken`:

```powershell
$billingHeaders = @{ Authorization = "Bearer $billingAccessToken" }
Invoke-RestMethod 'http://localhost:8009/payments?limit=25&status=succeeded' -Headers $billingHeaders
Invoke-RestMethod 'http://localhost:8009/commission-totals?purpose=consultation' -Headers $billingHeaders
```

Use the disposable PostgreSQL setup and explicit reset flags in `README.md`.
`python -m pytest tests/test_queries.py -q` verifies ownership, tenant isolation,
combined and revoked roles, authentication/identity failures, tied timestamps,
filters/cursor scope, financial snapshots, refund exclusions, delivery-fee
handling, empty totals and the safe-integer boundary. The full billing suite
also retains checkout, webhook, worker and migration regression checks.
Synthetic identities/payment rows in these checks do not establish real Stripe,
frontend, scheduling/refund or AWS integration.

Observed on 18 October 2026: 228 billing tests plus 38 subtests passed against
actual local PostgreSQL, including 27 B05 checks. Ruff lint/format and `pip check`
passed. Actual loopback HTTP verified token authentication, patient list scope,
concealed detail, clinic/platform totals and immediate membership revocation;
the identity transport and payment rows were synthetic. The existing Starlette
TestClient deprecation warning remains. CI additionally runs PostgreSQL 17;
the local disposable cluster uses PostgreSQL 18.
