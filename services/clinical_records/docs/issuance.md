# R03 prescription issuance and publication

POST `/api/v1/clinical-records/prescriptions/{prescription_id}/issue` accepts no body
or an empty object. It uses the existing Cognito/JWKS and identity checks, then
locks the prescription row and revalidates all appointment context through
scheduling. Only the assigned active doctor during `in_progress` can issue or
repeat issuance. Unrelated, cross-tenant and administrative callers receive 404.
An authorized caller outside the writing state receives 409.

A draft must have nonempty valid, unique medication items that are still active
in the owning clinic's fulfilment catalogue. The draft's server-supplied name
snapshots remain intact. Issuance sets `status=issued` and the database-clock
`issued_at`, then stages an event through M02 `add_event` in the same transaction.
Any storage failure rolls back both changes. Editing and issuance take the same
parent row lock, so edits cannot cross the freeze boundary. Issued/voided content
cannot be edited through these routes. Repeated issue requests return the original
resource without changing timestamps or consulting a possibly changed catalogue.
Current identity and appointment checks still apply to those retries.

The event ID is UUIDv5 of `telelink:prescription_issued.v1:<prescription_id>` in the
standard URL namespace. This gives each prescription one stable logical issuance
identity, stored as the outbox primary key. The initiating workflow correlation ID
is the appointment ID; downstream consumers propagate it. Source is
`telelink.clinical-records`, type is `prescription_issued.v1`, and C05 data contains
only `prescription_id` and `appointment_id`, with tenant/correlation/time metadata
in the envelope. No notes, item payloads, medication names or instructions enter
the event or ordinary logs.

Migration `0003` adds `clinical_records.event_outbox` using the shared M02 table
definition, including its pending-work index. Upgrade before deploying the HTTP
process or worker. Downgrading to `0002` drops queued/publication history; use this
only on a disposable database, or after explicitly reconciling retained events.
The HTTP readiness check expects `0003`. There is no schema access to other
services from the runtime.

Run `python -m app.publish_events` in a separate worker using the service `.env`.
`--once` publishes at most ten due entries and prints the published/failed counts.
The worker uses shared AWS client construction and M02 `publish_pending`, which
locks due rows with `SKIP LOCKED`, tracks successful `published_at`, and retains
the original envelope for failures. Backoff starts at five seconds and caps at
five minutes. A crash after provider acceptance but before saving its outcome can
resend the same event ID; M03 consumer deduplication remains required. Do not prune
pending events or replace their identities to recover from a provider failure.

Inspect pending metadata without selecting clinical content:

```sql
SELECT event_id, attempts, last_error, next_attempt_at
FROM clinical_records.event_outbox WHERE published_at IS NULL;
```

## Verification — 15 October 2026

Focused PostgreSQL 17 tests run under the restricted clinical-records role. They
cover authorized issuance, concurrent duplicate requests, editing raced against
issuance, exact C05 envelope shape, metadata-only payloads, stable retries,
revocation and context concealment, invalid/empty/inactive items, provider outage,
outbox-insert and pre-commit rollback, and M02 timeout/throttling backoff followed
by successful publication with the same stored envelope. The full existing API,
adapter and migration suite also runs, including fresh/repeated upgrade,
downgrade/re-upgrade, metadata drift and unrelated-schema isolation.

A local HTTP walkthrough used real Floci PKCE/JWKS, identity, scheduling and
records, with an explicitly synthetic C04 catalogue HTTP fixture. A disposable
in-progress appointment was seeded only for test setup; no payment/consultation
workflow integration is claimed. Patient/clinic/platform issuance was concealed;
the assigned doctor created and issued a prescription, then repeated issuance
returned the same resource. M02 published its committed event into a uniquely
named Floci event bus and SQS document queue. The received body parsed with the
C05 document consumer parser, retained the stable event/correlation IDs and
excluded clinical text. Publication tracking prevented another send after success.
Synthetic rows and isolated messaging resources were removed afterward.

Real fulfilment catalogue integration, service-only PDF/dispensing projections,
PDF generation, browser and AWS checks remain unverified. Read/write decisions
use scheduling's current HTTP response; there is no distributed transaction
spanning its later state changes and the clinical commit. R02 evidence remains
in [api.md](api.md), which describes the earlier pre-issuance implementation.
