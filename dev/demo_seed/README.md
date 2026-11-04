# Repeatable local demo seed (RF07)

This command saves the clean demo dataset as source code. It supports the Windows
**host launcher** in `dev/local_stack.ps1`, with its existing PostgreSQL 17,
Floci and Redis containers. It does not support running Compose API replicas.
Use the existing [host setup](../../docs/I02-local-journey.md) first: all nine
services must have local `.env` files, migrated schemas and their virtualenvs.
The local Cognito pool/public SPA client and document/branding buckets must already
exist through the normal bootstrap. It does not create or migrate infrastructure.

From the repository root, install the small seed dependencies into the identity
virtualenv. The document virtualenv renders PDFs with its installed ReportLab
templates; no generated PDFs are committed.

```powershell
services/identity/.venv/Scripts/python.exe -m pip install -r dev/demo_seed/requirements.txt
```

The default invocation is a **read-only preflight**. It does not stop services,
write configuration, create backups or reset data:

```powershell
services/identity/.venv/Scripts/python.exe dev/demo_seed/seed.py
```

To explicitly replace the local demo data, run this one command:

```powershell
services/identity/.venv/Scripts/python.exe dev/demo_seed/seed.py --reset
```

For a private Tailscale frontend, supply its browser origin so generated logo URLs
and local notification links use that address. This does not configure Tailscale
or change Cognito callback URLs:

```powershell
services/identity/.venv/Scripts/python.exe dev/demo_seed/seed.py --reset --app-origin https://your-machine.your-tailnet.ts.net
```

`--root <checkout>` can target an existing configured host checkout when running
the tool from a different worktree. All generated state stays in that checkout's
ignored `.local/demo-seed/`. No fixed drive letter or personal hostname is required.

## Reset scope and safeguards

`--reset` stops tracked host processes and the existing Docker Stripe listener,
then backs up the database, Redis data, persistent Floci state, service/frontend
configuration and any configured delivery directories. Backups are timestamped
under `.local/demo-seed/backups/`; the PostgreSQL archive is listed/validated and
its checksum is checked again before resetting. A failed backup prevents reset.
Backups contain local configuration secrets and must remain private/ignored.

After backup, it replaces:

- Users in the one `telelink-local` Cognito pool, preserving the pool, public app
  client, callback URLs, groups and infrastructure configuration.
- Rows in the nine application-owned schemas, including stale audit/event/job
  state. Schemas, constraints and `alembic_version` migration records remain intact.
- Objects in the configured `telelink-local-*` document and branding buckets,
  messages in `telelink-local-*` queues, and the dedicated Redis database 0.

Configured service databases must all be the same loopback `telelink` database,
using their service-owned usernames, and match the published port of the host
guide's PostgreSQL container. Floci/Redis targets must match their local container
ports. Every service must explicitly set `SERVICE_ENVIRONMENT=local`. Database,
environment, AWS-endpoint and Redis `SERVICE_*` process overrides are refused.
Delivery configuration files must be inside the selected checkout's `.local/`.
Do not share these dedicated development resources with other applications.

The seed uses only dummy AWS credentials against Floci. It creates no Stripe
Checkout/payment/refund and makes no courier quote/order/tracking request. Existing
Stripe sandbox destination mappings and configured sandbox contact/location
examples are remapped to the new local IDs; provider credentials are preserved.
Delivery directories are optional, but if configured they must already be valid.
The tool does not fabricate provider credentials, sender contacts or coordinates.

After seeding, all APIs and workers restart, then the real local APIs verify
accounts, clinic-scoped records, patient lists, PDF downloads and access denial.
The Tailscale gateway is left running. Sign out and sign in again after reset;
previous Cognito identities and browser sessions no longer match the new accounts.

## Dataset and login

Every account uses the local-only password `LocalDemo123!`:

| Account | Demo role |
| --- | --- |
| `patient@example.test` | Primary patient |
| `patient2@example.test` | Second patient |
| `doctor@example.test` | Harbour clinic doctor |
| `doctor2@example.test` | Orchard clinic doctor |
| `clinic@example.test` | Clinic administrator for all five examples |
| `clinic2@example.test` | Orchard administrator, revoked Harbour access |
| `staff@example.test` | Revoked membership example; intentionally no active workspace |
| `platform@example.test` | Platform administrator |

The seed contains 5 clinics (2 active, pending, rejected and suspended), 32
appointments, 14 medication orders and 42 clearly marked sample PDFs. Branding,
prices, commission rates, staff roles, medicines/instructions, notes, prescriptions,
MC periods, payment breakdowns, addresses, preparation and delivery states have
examples. All six payment statuses and several delivery outcomes are simulated
database snapshots, not evidence of provider integration. Any later deliberate
UI action still uses the application's configured sandbox integrations.

Business IDs are deterministic across resets; Cognito subjects are recreated and
linked correctly. Appointment times are recalculated relative to the current
Singapore date. Held bookings/quotes expire normally after their short allowed
lifetime. Simulated active deliveries are not queued for provider submission or
polling. Temporary admissions, authentication tokens, idempotency keys and event
inbox/outbox rows are not fabricated merely to fill internal tables.

The generated `.local/demo-seed/README.md`, `manifest.json`, `field-coverage.json`
and `verification.txt` record the actual run. Coverage checks require at least
one non-null example in every column of the 19 core business tables (231 fields
at RF07), using different rows for mutually exclusive fields.

To check the last saved run again without reset:

```powershell
services/identity/.venv/Scripts/python.exe dev/demo_seed/seed.py --verify
```

Verification calls the local APIs directly, independent of Tailscale routing.
Document downloads retain the existing localhost-only signer restriction when
viewed from a different device. This tool does not change application contracts,
provider integration, authentication policies or that download limitation.

## Recovery

On failure before reset starts, the launcher is restarted. On a seed failure after
reset begins, processes remain stopped and the command prints the backup path.
Fix a missing dependency/configuration and rerun `--reset` to make a fresh demo,
or restore the matching database **and** Floci snapshots to recover old identities.
Do not restore the old database while retaining the new Cognito users.

For PostgreSQL, stop the host launcher and Stripe forwarder, copy
`<backup>/database.dump` into the PostgreSQL container, and run:

```powershell
docker cp "<backup>/database.dump" telelink-clinic-postgres:/tmp/demo-restore.dump
docker exec telelink-clinic-postgres pg_restore -U postgres -d telelink --clean --if-exists /tmp/demo-restore.dump
```

To restore Floci without mixing old/new files, stop its container, create a fresh
named volume, and copy `<backup>/floci-data/` into that volume using a temporary
container. Point the root Compose `floci` service at that volume through an ignored
override before starting it. Preserve the previous volume until recovery is
verified. Restore changed `.env` files from `<backup>/config/`, and copy the saved
`SERVICE_DELIVERY_*_PATH.json` files back to their paths from the restored fulfilment
configuration. Redis can remain cleared because its locks/cache are temporary.
Start Floci and the existing host launcher, then verify old account access.
No automatic rollback or backup deletion is performed.

## Checks

```powershell
services/identity/.venv/Scripts/python.exe -m unittest discover -s dev/demo_seed -p "test_*.py" -v
services/identity/.venv/Scripts/python.exe -m ruff check dev/demo_seed --config services/template/pyproject.toml
```

The offline tests exercise target validation, read-only preflight, missing/tampered
backup rejection and the no-mutation boundary. Live seed states must be checked
against disposable storage when changing the dataset; do not reset a teammate's
running demo just to test packaging.

RF07 verification (23 October 2026): Ruff and 13 offline safeguard tests passed.
Two full backup/reset/seed/render/coverage cycles ran on disposable PostgreSQL,
Redis and Floci containers. Both retained all nine migration markers, recreated
all eight working logins, populated the 19 business tables and produced the same
8/5/32/14/42 account/clinic/appointment/order/PDF counts with stable business IDs.
The packaged `--verify` also passed against the existing running host demo without
resetting it. The Windows launcher stop/start sequence was previously exercised
for that demo; automated CI runs the offline safeguards, not the destructive
integration exercise. AWS, provider transactions and remote PDF signing remain
outside this tooling's verification scope.
