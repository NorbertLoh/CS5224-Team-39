# Billing persistence (B01)

Billing owns the `billing` schema and payment attempts for consultation and
medication/delivery charges. It stores provider references and immutable price
and commission snapshots following C01/C03/C04. B01 supplies persistence only;
checkout, webhooks, payment APIs, refunds and event workers follow in their own
tasks. No provider credentials or real payments are needed for these checks.

## Install

From `services/billing`, with Python 3.10+:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common -e .
```

Versions reuse the existing service foundation lockfile, omitting its unused
HTTP-server packages. The shared package still brings its declared
technical dependencies; no shared domain model is introduced.

## Fresh disposable database

The example database is for B01 verification and can lose billing data during
tests. Keep it separate from the persistent clinic database on port 55411 and
root Compose volumes. The credentials below are synthetic local values.

```powershell
docker run --name telelink-b01-postgres --label telelink.task=B01 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=b01-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55414:5432 -d postgres:17
docker exec telelink-b01-postgres pg_isready -U postgres -d telelink
```

Wait for `accepting connections`. Provision once as administrator:

```powershell
Get-Content -Raw scripts/create-local-schema.sql | docker exec -i telelink-b01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
Get-Content -Raw scripts/create-test-sentinel.sql | docker exec -i telelink-b01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
```

Provisioning intentionally fails when its role/schema already exists. Reuse this
container with `docker start telelink-b01-postgres`; do not rerun provisioning.
The service role owns only `billing`. The sentinel script grants read-only access
to unrelated test objects to verify isolation; do not use that script in production.

## Migrate

Alembic reads the exported URL, not `.env` files. `.env.example` documents the
sanitized configuration. Use the restricted billing role for migrations:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://billing:local-demo-only@127.0.0.1:55414/telelink'
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic check
```

Repeat upgrade is safe. Revision `0001`, the version table, indexes and update
trigger belong only to `billing`. Reflection excludes other schemas. An intentional
`alembic downgrade base` deletes all payment rows and the billing table/function,
retaining the provisioned schema and version table. Re-upgrade recreates them.
Do not run reset-enabled tests or destructive downgrades on a development/demo
database. Run controlled migrations before later service deployments; never
execute them on every replica startup.

## Stored facts

- `consultation` links one appointment and has no order/quote. Its delivery fee
  is zero. `medication_delivery` links an order and quote, with no appointment.
  External UUIDs have no cross-service foreign keys.
- Amounts are SGD integer minor units between 0 and 9007199254740991.
  `amount_minor = commissionable_minor + delivery_fee_minor`. Commission is
  `floor(commissionable_minor * commission_bps / 10000)` for rates 0–10000;
  delivery fees are excluded. Validation uses numeric multiplication to avoid
  bigint overflow. `clinic_amount_minor` is total minus commission, including
  delivery cost, and does not represent a net Stripe settlement.
- Ownership, links and financial snapshots cannot change after insertion, even
  through direct SQL. The trigger preserves `created_at` and refreshes `updated_at`.
  Timestamps use UTC and the ORM fetches database-generated values.
- Status is `pending`, `failed`, `succeeded`, `refund_pending`, `refund_failed` or
  `refunded`. Resolution is `none`, or `refund_required` for a succeeded payment
  or incomplete refund. A refunded row clears the review flag.
- Provider checkout/payment IDs and provider checkout idempotency keys are opaque,
  nonblank when present, and unique per provider/account. A null account denotes
  the platform-account namespace; null references do not conflict. PostgreSQL 17
  partial unique indexes use `NULLS NOT DISTINCT` for this distinction.
- Multiple attempts for an appointment/order remain representable. A late success
  on a failed attempt can be recorded beside another success and flagged for
  review. B02/B06 must coordinate one current checkout transactionally; this
  persistence layer does not establish provider authority or checkout concurrency.

For example, a medication subtotal of 2000 plus delivery of 500 at 1000 basis
points stores total 2500, commission 200 and clinic amount 2300.

Provider references are internal. No HTTP serializer exists here; future APIs
must explicitly project the C03 public fields. No card data, provider secrets,
clinical content, addresses or raw webhook payloads are stored.

## Verification

Use only the disposable database provisioned above. Tests downgrade/delete billing
data and require explicit opt-in:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://billing:local-demo-only@127.0.0.1:55414/telelink'
$env:BILLING_TEST_ALLOW_RESET='1'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pip check
```

Without `TEST_DATABASE_URL`, persistence checks explicitly skip. Supplying a URL
without reset consent fails before migration. The suite covers migration parity
and round-trips, sentinel preservation, restricted permissions, valid and invalid
money/resource/state combinations, provider namespaces, retry history and SQL/ORM
snapshot protection. It does not prove Stripe, scheduling or fulfilment integration.
The billing CI workflow runs these checks against PostgreSQL 17 on Python 3.10.

Observed verification on 16 October 2026: PostgreSQL 17 with Windows/Python 3.13
passed all 89 tests; Ubuntu/Python 3.10 CI passed the same 89 tests. Ruff lint and
format checks and `pip check` passed. Missing reset consent was rejected before
migration; without a test URL the result was 1 passed and 88 explicit skips.
Offline migration SQL generation also succeeded without a database connection.
These results verify the persistence foundation, not provider or AWS integration.

Stop only this test container when finished:

```powershell
docker stop telelink-b01-postgres
```
