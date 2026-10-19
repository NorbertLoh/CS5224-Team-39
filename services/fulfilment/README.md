# Fulfilment

D03 adds `POST /orders/{order_id}/ready`; policy, retries and verification are
documented in [`READINESS.md`](READINESS.md). No additional migration or setting is needed.

D04 consumes medication-payment events in a separate process. Run migration `0003`
and configure the billing service credential and queue described in [`PAYMENTS.md`](PAYMENTS.md).

D05 adds guarded delivery submission and verified uncertain-outcome reconciliation.
Run migration `0004`; worker, private contacts and recovery setup are documented in
[`DELIVERIES.md`](DELIVERIES.md).

D06 adds verified provider polling with persisted scheduling. Apply migration `0005`
and run the separate worker documented in [`TRACKING.md`](TRACKING.md).

D02 quotation APIs, sandbox setup and verification are documented in
[`QUOTES.md`](QUOTES.md). Run migration `0002` before starting the updated service.

X05's isolated Lalamove sandbox CLI and callback verifier are documented in
[`docs/lalamove-spike.md`](../../docs/lalamove-spike.md). They do not update
application orders or implement D02/D05/D06.

Owns the `fulfilment` PostgreSQL schema, clinic medication catalogue, prescription-linked
orders, item snapshots and persistent order-request keys. Uses C01/C04 and the shared
access-token verifier/current identity lookup. No other service's tables are accessed.

## Setup

From `services/fulfilment`, in a dedicated Python 3.10+ environment:

```powershell
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps --no-build-isolation -e ../../packages/python_common -e .
Copy-Item .env.example .env
```

On a fresh disposable `telelink` database, run `scripts/create-local-schema.sql` as the
PostgreSQL administrator. It creates the restricted `fulfilment` role/schema using
synthetic local credentials. Set `SERVICE_DATABASE_URL` to that role, then:

```powershell
python -m alembic upgrade head
python -m app
```

Set issuer, reachable JWKS, SPA client ID and `SERVICE_IDENTITY_URL` to the running
identity service's local address. The identity URL is the service root (`/me` is
appended). Configure `SERVICE_CURSOR_SECRET` with a private value of at least 32 bytes
shared between service replicas. Cursors expire after 15 minutes and bind current
permissions, endpoint, filters and page size. Missing pagination configuration fails
closed when a next cursor is needed. Protected endpoints fail closed without identity
and token configuration; no header bypass exists. Readiness verifies the migrated
orders table and requires database configuration.

Direct service paths are listed below. An ingress strips `/api/v1/fulfilment` before
forwarding; `SERVICE_ROOT_PATH` is OpenAPI metadata, not a router prefix. D01 does not
change shared Compose, frontend routing, infrastructure or contracts.

## APIs

| Method / path                                        | Policy / result                                                      |
| ---------------------------------------------------- | -------------------------------------------------------------------- |
| GET `/clinics/{tenant_id}/catalogue`                 | Active owning-clinic doctor/admin; active items only                 |
| PUT `/clinics/{tenant_id}/catalogue/{medication_id}` | Active owning-clinic admin; 201 new / 200 updated                    |
| POST `/orders`                                       | Own patient, issued prescription; 201 new / 200 existing or replay   |
| GET `/orders/{order_id}`                             | Own patient, active owning-clinic admin or platform operational role |
| GET `/orders`                                        | Same scoped policy, optional `tenant_id` / `status`                  |

Catalogue writes accept only `display_name`, `unit_label`, `unit_price` (nonnegative
integer SGD Money) and `active`. POST orders accepts only `prescription_id` and requires
`Idempotency-Key` (1–64 ASCII letters/digits/`.`/`_`/`-`). Quantities and links come from
the dispensing source; prices/names come from the owning clinic's active catalogue.
Missing/inactive medicine gives 409 `medication_unavailable`. Overflow of safe JSON
integer totals gives 409 `amount_out_of_range`.

Orders start `awaiting_payment` / `not_ready` / `unpaid`, with null quote/payment/delivery
IDs and null delivery fee/total. Their subtotal and item amounts are server-calculated.
They contain no notes, instructions, addresses or provider content. Order creation never
mutates an existing order, including a cancelled order. Catalogue updates leave stored
snapshots unchanged; D02 must refresh prices for each new quote before B06 checkout.

A unique database constraint enforces one order per prescription across all tenants
and patients. Transaction-scoped PostgreSQL locks serialize subject/key and prescription
creation. Keys are scoped to authenticated subject and the create-order operation and
retained indefinitely (at least C03's 24 hours). Same key/body replays its original stored
response with 200; different body gives 409 `idempotency_conflict`. A new key for an
existing prescription returns that order's current state. Each request rechecks current
identity; keys cannot expose another patient's order. Failed attempts roll back keys and
orders together. Catalogue rows are locked in medication-ID order while snapshotting.

Both collections use `{items,next_cursor}`, default limit 25, range 1–100. Catalogue
ordering is `display_name,medication_id`; order ordering is `created_at,order_id`.
Roles/memberships are read again per request. Doctors cannot read operational orders
solely through clinic membership, and platform admins cannot write a clinic's catalogue.
Platform-only operational responses omit `items` (medication IDs, names and quantities);
the owning patient and active owning-clinic admins receive the full order shape.

## Dispensing integration boundary

D07 supplies a real `HttpDispensing` adapter and an audited, minimum clinical-records
projection. Configure `SERVICE_RECORDS_URL` (including `/api/v1/clinical-records`)
and `SERVICE_RECORDS_SECRET`, matching records' `SERVICE_FULFILMENT_SECRET`.
Only correctly linked issued prescriptions can create/reserve orders. Service JWTs
are short-lived and purpose-bound; clinical instructions never enter the projection.
Unconfigured or unavailable upstreams fail closed.

`SERVICE_DISPENSING_FIXTURE_PATH` remains an explicit local/test-only alternative
for the agreed synthetic C04 projection. It cannot be enabled with the real records
URL and is never an error fallback. Catalogue records are not auto-seeded.

D07 also implements billing's atomic checkout reservation and patient-scoped failed
attempt reconciliation. Setup, live pages, worker requirements and actual sandbox
verification are in [`docs/D07-live-fulfilment.md`](../../docs/D07-live-fulfilment.md).
The full doctor-issued/physical delivery journey remains I03; no public provider
callback route is exposed.

## Verification

Use a fresh disposable database; these tests truncate only fulfilment tables and
exercise downgrade to base. Before tests, run `scripts/create-local-schema.sql` and
`scripts/create-test-sentinel.sql` as administrator:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://fulfilment:local-demo-only@localhost:5432/telelink'
$env:FULFILMENT_TEST_ALLOW_RESET='1'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

Checks cover fresh/idempotent migrations, drift and rollback, restricted credentials,
database constraints, current-role access, real signed-token verification with a mock
identity HTTP transport, retry conflicts and concurrent creation, trusted totals,
catalogue validation, cursor binding and fixture fail-closed configuration. These are
local PostgreSQL/service checks. D07 records separate actual HTTP/provider evidence
in the linked integration document.
