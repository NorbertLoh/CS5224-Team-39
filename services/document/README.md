# Document service (P01/P02/P03)

Metadata persistence and simple PDF templates for prescriptions, receipts and
medical certificates (MC). P02 (issue #128) adds prescription queue processing,
private S3 storage and a document-ready outbox. P03 adds an authenticated HTTP API
for audited document lists and short-lived signed downloads; see [API setup and
access policy](docs/api.md). Worker setup, recovery and verification:
[P02 worker](docs/worker.md). Root Compose and frontend integration remain separate.

## Setup and migrations

Run from `services/document` with Python 3.10+:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock.txt
.venv/Scripts/python -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
```

On a **fresh disposable** PostgreSQL 17 database named `telelink`, run
`scripts/create-local-schema.sql` as the database administrator. It creates the
`document` role and its schema, using synthetic local credentials. Do not run
this bootstrap on an existing or production database. Production provisioning
must supply its own role/secret and schema grants. Export the connection URL;
Alembic does not load `.env` files:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://document:local-demo-only@localhost:5432/telelink'
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic check
# Disposable database only; deletes document metadata:
.venv/Scripts/python -m alembic downgrade base
```

Alembic and its version table live exclusively in `document`. Provisioning is
separate from migration, so the service role cannot create other schemas. No
cross-service foreign keys are used. Required tenant, patient and appointment
IDs are external references; P02/P03 must verify them through authorised source
services before generation/access. Metadata constraints do not grant access.

`Document` supports `prescription_pdf`, `receipt_pdf` and
`medical_certificate_pdf`, with statuses `pending`, `ready`, `failed`. Each kind
requires exactly its own source ID (`prescription_id`, `payment_id`, or
`medical_certificate_id`). Clinical kinds also require the assigned `doctor_id`.
Uniqueness on tenant/kind/source reserves one document per source, including
failed attempts; P02 should retry that row rather than insert a replacement.
`ready` requires bucket, key, positive byte size and SHA-256; pending/failed rows
have no object metadata. Object references are unique. Buckets/keys are internal
metadata and must never appear in public document-list responses.

Creation times are immutable and a PostgreSQL trigger updates `updated_at` on
every update, including raw SQL. Patient and appointment indexes support the
planned C01 pagination. The schema neither stores clinical content nor enforces
the later worker's generation lifecycle or object privacy policy.

## Rendering

Construct validated snapshots from `app.template_data`, then call
`render_prescription`, `render_receipt`, or `render_medical_certificate` from
`app.templates`. Each returns PDF bytes without network or storage side effects.
See `tests/test_templates.py` for complete synthetic examples.

- Prescription: clinic/patient/reference/issue time, doctor/registration,
  medication names, quantities and instructions.
- Receipt: clinic/patient, payment reference/time, SGD integer-minor-unit lines
  and a total that must match their sum. Supply trusted successful-payment
  snapshots; rendering does not establish payment success or calculate tax.
- MC: clinic/patient, consultation date, inclusive unfit-for-duty period and
  issuing doctor/registration. No diagnosis or invented signature is added.

All timestamps require an offset and display in Asia/Singapore. Text is escaped
before PDF layout, long text wraps/paginates, and pages have numbered privacy
footers. The bundled ReportLab Bitstream Vera fonts include their own licence
and support a limited character repertoire. Unsupported characters (including
CJK) raise `ValueError`; add a properly licensed font with glyph coverage before
supporting those names. These are prototype templates, not signed documents.

U17 connects MC source persistence, authoritative consultation completion and
the document worker/download path. MC additional notes are supported; unavailable
clinic address/doctor registration fields are omitted. See
[MC setup, contracts and verification](../../docs/medical-certificates.md).
Receipt issuance and live source integration remain separate work.

## Verification

Provision `scripts/create-test-sentinel.sql` as administrator in the disposable
test database after creating the document role. Tests require explicit reset
consent and downgrade/delete **all document metadata**:

```powershell
$env:TEST_DATABASE_URL=$env:SERVICE_DATABASE_URL
$env:DOCUMENT_TEST_ALLOW_RESET='1'
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

Without `TEST_DATABASE_URL`, persistence tests skip; PDF tests still run. The
document CI workflow runs real PostgreSQL checks as the restricted service role:
fresh/repeated upgrade, metadata parity, downgrade/re-upgrade, public-schema
preservation, source uniqueness, storage constraints and timestamp updates.
PDF checks parse all three outputs and cover multi-page instructions, literal
markup, supported Unicode, invalid totals, timezone offsets and MC date ranges.
