# Database, schemas and migrations

PostgreSQL 17 stores TeleLink data in one `telelink` database, with a schema and
login role per owning Python business service. Local Compose uses a persistent
Docker volume; AWS uses private encrypted RDS. Redis mirrors temporary booking
holds, S3 stores PDF/image bytes, and Cognito owns authentication credentials.

## Ownership and table map

A schema is a **service boundary**, not a clinic. Tenant-owned rows carry clinic
IDs and are filtered by service authorization. PostgreSQL schema isolation alone
does not enforce tenant access or grant access to another clinic's clinical data.

| Schema / DB role | Main domain tables | Definition and guide |
| --- | --- | --- |
| `identity` | `subjects`, `patient_profiles`, `memberships`, `doctor_documents`, `doctor_applications`, `doctor_application_events`, `doctor_photos` | [Models](../../services/identity/app/models.py), [README](../../services/identity/README.md) |
| `tenant` | `clinics`, `audit_events`, `clinic_locations` | [Models](../../services/tenant/app/models.py), [README](../../services/tenant/README.md) |
| `scheduling` | `availability_slots`, `appointments`, payment/recovery records | [Models](../../services/scheduling/app/models.py), [README](../../services/scheduling/README.md) |
| `consultation` | `sessions`, `admissions`, `signalling_nodes`, `room_assignments` | [Models](../../services/consultation/app/models.py), [README](../../services/consultation/README.md) |
| `clinical_records` | `notes`, `prescriptions`, `prescription_items`, `prescription_corrections`, `medical_certificates`, read audits | [Models](../../services/clinical_records/app/models.py), [README](../../services/clinical_records/README.md) |
| `billing` | `payments`, `refund_attempts`, checkout attempts/keys, `stripe_webhook_events` | [Models](../../services/billing/app/models.py), [README](../../services/billing/README.md) |
| `document` | `documents`, `access_audits`, private S3 object references | [Models](../../services/document/app/models.py), [README](../../services/document/README.md) |
| `fulfilment` | `catalogue_items`, `orders`, `order_items`, `order_requests`, `prescription_prices`, `prescription_correction_holds`, `quotes`, `quote_requests`, `deliveries` | [Models](../../services/fulfilment/app/models.py), [README](../../services/fulfilment/README.md) |
| `notification` | `jobs`, event inbox and lifecycle-email records | [Models](../../services/notification/app/models.py), [README](../../services/notification/README.md) |

This map is not an exhaustive DDL dump. Each owner's
`services/<owner>/migrations/versions/` defines applied-schema history, including
indexes, checks, functions and triggers absent from a simple ORM diagram.
`app/models.py` describes ORM tables. Use `alembic heads` for current code revisions;
old task notes can reference older heads. The optional `template` schema is not
one of the AWS nine. Signalling uses consultation APIs, not a separate DB schema.

## Relationships and consistency

```mermaid
flowchart LR
    I[Identity: subjects and memberships] -. Authorized HTTP .-> S[Scheduling: slots and appointments]
    T[Tenant: clinic and prices] -. Authorized HTTP .-> S
    S -. Participant context .-> C[Consultation: sessions and admissions]
    C -. Authorized operations .-> R[Clinical records: notes and prescriptions]
    S -. Appointment and payment events .-> B[Billing: payments and snapshots]
    R -. Issued events .-> D[Document: PDF metadata]
    R -. Dispensing projection .-> F[Fulfilment: orders and delivery]
    F -. Payment events .-> B
    B -. Verified receipt source .-> D
    D -. Document-ready events .-> N[Notification: durable jobs]
```

Dashed arrows are logical references/API or event dependencies, **not SQL foreign
keys across schemas**. Within a service, foreign keys enforce its relationships:
scheduling binds appointment clinic/doctor/times to the slot and enforces one
active reservation per slot. External UUIDs are checked through owner interfaces.

Services do not join/write another owner's tables to implement workflows. Money
uses integer minor units and trusted snapshots; later clinic price edits do not
rewrite stored appointment/payment snapshots. Timestamps are timezone-aware UTC;
the UI presents Singapore dates. See [contracts](../../contracts/README.md).

Producer-owned outboxes and consumer-owned inboxes make retries durable across
restarts without a cross-service DB transaction. Do not delete inbox rows or
invent new event IDs to force replay. See [messaging recovery](../messaging-replay.md).

## Local setup and migrations

For the whole stack, from the repository root:

```powershell
./dev/compose.ps1 setup -Payments
# Only when adopting the supported existing host database instead:
# ./dev/compose.ps1 setup -UseExistingDatabase -Payments
```

The helper provisions missing roles/schemas, runs every owner's `alembic upgrade
head`, preserves records and starts services after setup. It never uses
`down --volumes`. Do not mount an adopted volume in two running PostgreSQL
containers. See [Compose setup](../compose-stack.md).

For isolated development, use the service README to install locked dependencies
and provision a fresh schema with `scripts/create-local-schema.sql`. These
standalone SQL scripts fail when roles/schemas exist; they are not upgrade/reset
commands. From the owner service directory with its virtualenv:

```powershell
$env:SERVICE_DATABASE_URL = 'postgresql+psycopg://OWNER:ENCODED_PASSWORD@HOST:PORT/telelink'
.venv/Scripts/python.exe -m alembic heads
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic check
```

Substitute actual configuration; keep credentials private and percent-encode
special URL characters. Alembic requires the exported URL; do not assume `.env`
is loaded. Each schema owns an `alembic_version`; there is no global head.
Connections use UTC and `search_path=public`; ORM/schema and migration filters
explicitly select the owner. Do not rely on a user-named search path.

Add migrations only under the owner: update models, generate a revision, review
upgrade/downgrade SQL and data guards, then verify on a disposable DB. Commit a
new revision instead of editing applied history. Autogeneration cannot infer all
renames, triggers or data migrations. See the [Alembic guide](../../services/template/docs/database.md).

## AWS bootstrap and migration tasks

[Bootstrap](../../infra/modules/demo-platform/bootstrap_database.py) reads the
RDS master secret and service database URLs at runtime, validates owner/host/DB,
revokes public schema creation, installs `btree_gist` for scheduling's UUID/time
exclusion constraint, creates missing roles/schemas and applies configured
passwords. It creates no domain tables or demo records. Rerunning can change DB
passwords, so coordinate secrets and task rollout.

After publishing a complete image map with workloads disabled, run
`terraform output -json platform` in the demo root. It exposes `cluster_name`,
`bootstrap_task`, `migration_tasks` and `task_network_configuration`. Use those
exact values with AWS CLI `ecs run-task` (Fargate), `ecs wait tasks-stopped` and
`ecs describe-tasks`. Pass the network JSON via an ignored local file, using the
emitted private subnets/security group rather than unrelated copied values.

For example, in PowerShell 7 from the repository root after reviewing the outputs:

```powershell
$demoPlatform = terraform -chdir=infra/envs/demo output -json platform | ConvertFrom-Json
New-Item -ItemType Directory -Force .local | Out-Null
$demoPlatform.task_network_configuration | ConvertTo-Json -Depth 10 |
    Set-Content -Encoding utf8NoBOM .local/demo-task-network.json
$demoTaskArn = aws ecs run-task --cluster $demoPlatform.cluster_name `
    --launch-type FARGATE --task-definition $demoPlatform.bootstrap_task `
    --network-configuration file://.local/demo-task-network.json `
    --query 'tasks[0].taskArn' --output text
# Stop if run-task failed or returned no task ARN; inspect its failures first.
aws ecs wait tasks-stopped --cluster $demoPlatform.cluster_name --tasks $demoTaskArn
aws ecs describe-tasks --cluster $demoPlatform.cluster_name --tasks $demoTaskArn `
    --query 'tasks[].{stopCode:stopCode,reason:stoppedReason,containers:containers[].{name:name,exitCode:exitCode,reason:reason}}'
```

Use the configured demo AWS profile/region. This example launches real work;
it is not a read-only diagnostic. After bootstrap succeeds, repeat with the task
definition from each `migration_tasks` entry (for example,
`$demoPlatform.migration_tasks.scheduling`), waiting and verifying each outcome.

Run bootstrap first, then all **nine** entries in `migration_tasks`. Each runs
`python -m alembic upgrade head` in its owner's image with its secret-injected URL.
A task ARN or STOPPED status alone is not success: inspect stop reason, container
exit codes and owning CloudWatch logs. Require zero exit codes before enabling
APIs, consumers and the demo seed. Serialize migrations per owner; Terraform
locking does not serialize manually launched ECS tasks. See [task definitions](../../infra/modules/demo-platform/migrations.tf).

Current AWS migration and runtime tasks reuse the owner's DB role. Separate
reduced runtime/migration grants remain production hardening work. Terraform
stores service secret ARNs rather than their values.

## Booking holds: PostgreSQL and Redis

1. Scheduling checks patient/clinic/doctor/price through current owner APIs, then
   locks the slot before appointment rows.
2. After locking, it reads PostgreSQL `clock_timestamp()`, expires elapsed holds
   and persists `hold_expires_at=min(server_now+10 minutes, slot_start)`.
   Equality means expired; checkout retries never extend the deadline.
3. A partial unique index covers `held`, `pending_payment`, `confirmed` and
   `in_progress`, preventing competing active bookings for the same slot.
4. Before releasing the slot lock, Redis mirrors the appointment UUID at
   `telelink:scheduling:hold:<slot_id>` with `PXAT` set to the persisted deadline.
   Compare-and-delete Lua only removes the old appointment's value, so delayed
   cleanup cannot erase a replacement hold.
5. The expiry worker runs bounded batches every five seconds and skips busy slot
   locks. Booking/withdrawal also expire lazily; Redis key notifications are not
   required to release elapsed capacity in PostgreSQL.

Missing Redis configuration rejects hold creation. A configured cache outage can
still allow a DB-safe hold to commit, while readiness returns 503. Missing/evicted
keys never release unexpired DB reservations; rollback can leave a harmless ghost
key until TTL expiry. Payment truth comes from verified billing/scheduling state,
not Redis. See [hold API and failure behavior](../../services/scheduling/docs/holds.md)
and [payment recovery](../../services/scheduling/docs/payments.md).

## Inspection, backup and rollback

An authorized role can inspect schema owners and applied revisions without
reading patient data:

```sql
SELECT schema_name, schema_owner
FROM information_schema.schemata
WHERE schema_name IN ('identity', 'tenant', 'scheduling', 'consultation',
  'clinical_records', 'billing', 'document', 'fulfilment', 'notification');
SELECT version_num FROM scheduling.alembic_version;
```

Back up before migrations and test restore separately. Managed AWS defaults keep
seven days of RDS backups, deletion protection and a final snapshot; the compact
profile keeps one day and skips the final snapshot. S3/Cognito/provider state
needs its own recovery plan; restoring the DB alone cannot restore the whole app.

Several downgrades deliberately refuse to destroy retained history or violate
constraints. Prefer a forward fix or reviewed restore; never delete business rows
to force a downgrade. DB suites downgrade/recreate tables: `TEST_DATABASE_URL`
must point only to a disposable DB with the service's sentinel/Redis fixtures,
never shared development/demo/production data.
