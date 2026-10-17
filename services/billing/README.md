# Billing persistence (B01)

Billing owns `billing.payments` for consultation and medication/delivery attempts,
provider references and immutable financial snapshots. Contracts define
[API conventions (C01)](../../contracts/api-conventions.md),
[payments (C03)](../../contracts/booking-payment.md) and
[orders/quotes (C04)](../../contracts/prescription-order-quote.md).
Checkout, webhooks, APIs, refunds and event workers follow in B02–B06.

The isolated [X03 Stripe spike](../../docs/stripe-spike.md) provides test-mode
Checkout/Connect verification commands and an explicitly labelled offline demo.
It does not implement billing application APIs or webhook verification.

The separate [X04 webhook spike](../../docs/stripe-webhook-spike.md) verifies
sample raw-body signatures using the Stripe SDK, without processing payments.

## Install

From `services/billing`, with Python 3.10+:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common -e .
```

## Fresh disposable database

Tests delete billing data. Use this separate PostgreSQL 17 database on port 55414,
away from the persistent clinic database (55411) and Compose volumes.
Credentials below are synthetic local values; no provider credentials are needed.

```powershell
docker run --name telelink-b01-postgres --label telelink.task=B01 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=b01-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55414:5432 -d postgres:17
docker exec telelink-b01-postgres pg_isready -U postgres -d telelink
```

Wait for `accepting connections`. Provision once as administrator:

```powershell
Get-Content -Raw scripts/create-local-schema.sql | docker exec -i telelink-b01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
Get-Content -Raw scripts/create-test-sentinel.sql | docker exec -i telelink-b01-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
```

Provisioning is one-time and fails if the role/schema exists. Reuse the container
with `docker start telelink-b01-postgres`. The role owns only `billing`; the
test-only sentinel script grants read access to unrelated objects for isolation checks.

## Migrate

Export the restricted-role URL explicitly; Alembic does not load `.env` files.
See [.env.example](.env.example) for configuration.

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://billing:local-demo-only@127.0.0.1:55414/telelink'
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic check
```

Repeat upgrade is safe; migration history and reflection stay within `billing`.
`alembic downgrade base` deletes payments and migration-owned objects, retaining
the provisioned schema/version table. Use downgrades and reset-enabled tests only
on disposable databases. Run migrations before deployment, outside replica startup.

## Persistence decisions

- External UUIDs have no cross-service foreign keys. A database trigger protects
  ownership, resource links and financial snapshots, preserves `created_at` and
  refreshes `updated_at`; timestamps use UTC.
- Commission validation casts to numeric before multiplication to avoid bigint
  overflow. Delivery fees are excluded; `clinic_amount_minor` includes delivery
  cost and is the gross non-platform amount, before provider settlement.
- Provider references remain internal and unique per provider/account. Partial
  indexes use `NULLS NOT DISTINCT` so a null account shares the platform namespace
  while absent references can repeat. Future APIs must project C03 public fields.
- Multiple attempts preserve retries and late/duplicate successes. B02/B06 must
  coordinate one current checkout; later handlers establish provider authority
  and legal state transitions. No card data, secrets or raw webhooks are stored.

## Verification

Use the disposable database above and explicitly allow its reset:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://billing:local-demo-only@127.0.0.1:55414/telelink'
$env:BILLING_TEST_ALLOW_RESET='1'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pip check
```

Without `TEST_DATABASE_URL`, persistence checks skip. A URL without reset consent
fails before migration. The suite covers migration parity/round-trips, schema
isolation, money/link/state constraints, provider namespaces, retry history and
SQL/ORM immutability. CI uses PostgreSQL 17 and Python 3.10.

Observed on 16 October 2026: all 89 PostgreSQL tests passed locally (Windows,
Python 3.13) and in CI (Ubuntu, Python 3.10), alongside Ruff and `pip check`.
Reset-consent rejection, explicit skips (1 passed, 88 skipped without a URL) and
offline migration SQL generation passed. Provider/AWS integration remains untested.

Stop only this test container when finished:

```powershell
docker stop telelink-b01-postgres
```
