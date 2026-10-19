# Notification foundation (N01)

This service owns notification jobs, three version-one email templates and the
`EmailSender` interface / SES implementation. N02 owns event consumption,
authoritative recipient resolution, send deduplication and automated status
transitions. There is no public send endpoint or running event consumer here.

## Setup

From this directory, with Python 3.10+:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock.txt
.venv/Scripts/python -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
```

Use a fresh disposable PostgreSQL database named `telelink`. As its administrator,
run `scripts/create-local-schema.sql` once to provision the local role and owned
`notification` schema. The script uses synthetic local credentials; deployment
must provision its own credentials and schema. Do not grant this role access to
other services' tables. Alembic never creates/drops another service's schema.

Copy `.env.example` to `.env` and adjust the database port if needed. The example
uses Floci on localhost:4566 and the frontend on localhost:5173. Database migrations
read the environment directly, so export `SERVICE_DATABASE_URL` before running:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://notification:local-demo-only@localhost:5432/telelink'
.venv/Scripts/python -m alembic upgrade head
```

Rollback: `python -m alembic downgrade base` drops notification jobs. It leaves the
schema, role and service-local Alembic version table in place. This deletes job
data; use only on the disposable development database.

`SERVICE_EMAIL_SENDER` is a single bare mailbox. `SERVICE_APP_URL` is the trusted
frontend base URL; templates append `/patient`. Deployed URLs require HTTPS.
`SERVICE_AWS_REGION` defaults to `ap-southeast-1`. In AWS, omit
`SERVICE_AWS_ENDPOINT_URL` and local dummy AWS credentials, use the task role with
`ses:SendEmail`, and verify sender/recipients as required by the SES sandbox.
Actual AWS SES setup/delivery remains W10. No shared Compose or routing changes
are required by this foundation.

## Local SES inspection

Start the existing pinned Floci 2.2.0 service with its default store-only SES
configuration. With the example environment loaded:

```powershell
.venv/Scripts/python -m app.check_local
```

The script permits only host-local Floci on port 4566 and the synthetic sender
`notifications@telelink.test`. It verifies this sender and
`n01-patient@telelink.test`, renders a booking email, sends it through the actual
adapter and checks the captured ID, sender, recipient, subject, plain text and HTML
at `http://localhost:4566/_aws/ses`. Each invocation intentionally creates one new
synthetic captured email. It does not create a job or consume application events.
No real recipient or deployed AWS email is used by this check.

## Persistence and delivery semantics

`notification.jobs` stores tenant/event/recipient IDs, recipient email, template
name, pending/sent/failed status, attempt count, SES message ID, safe error code
and creation/acceptance timestamps. It does not store clinical details or rendered
bodies. Treat recipient emails as private data; keep them out of logs and limit
DB access. Retention policy and recipient lookup are not implemented in N01.

The unique event/recipient/template key is schema groundwork for N02, not proof of
an idempotent sender. The three templates map to `appointment_confirmed.v1`,
`document_ready.v1` and `delivery_status_changed.v1`. Emails contain generic copy
and a sign-in link, without diagnosis, medication, signed downloads or tokens.
They do not grant access; the application still enforces its own authorisation.

`SESEmailSender.send()` returns the SES acceptance ID. `sent` means provider
acceptance, not delivery to an inbox. SES/network failures raise a sanitized
`EmailSendError`; persist only `ses_unconfirmed`, never raw provider messages.
There is no application retry loop here. SDK transport retries and ambiguous
network/crash outcomes can result in duplicate email; N02 must explicitly handle
these limits rather than claiming exactly-once delivery.

## Verification

Run against an explicitly disposable provisioned schema:

```powershell
$env:TEST_DATABASE_URL=$env:SERVICE_DATABASE_URL
$env:NOTIFICATION_TEST_ALLOW_RESET='1'
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```

On 19 October 2026, all 41 tests passed against isolated PostgreSQL 17. Checks
cover migration upgrade/repeated upgrade/schema drift/rollback/re-upgrade, default
values, duplicate keys, invalid states, acceptance metadata, templates, URL/header
validation, actual SDK request shapes and sanitized provider/connection failures.
Ruff passed. The actual local SES check verified one captured message's recipient,
subject and both bodies through Floci. Event integration, real AWS email delivery,
automated retries and bounce handling are not claimed.
