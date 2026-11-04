# I04: actual journey notifications through local SES

Verified on 22 October 2026 (Singapore time), after I03 merged in PR #249.
The existing N02 worker consumed actual retained I03 journey events, resolved
their current owners and patient, and dispatched three generic messages through
Floci's store-only SES. No artificial journey events were published, no business
or notification rows were seeded, and no real email delivery is claimed.

## Setup and rerun

Follow [I03](I03-local-journey.md) and the notification
[worker guide](../services/notification/WORKER.md). Provision notification's owned
schema in the existing local database on `55411`, install locked dependencies and
the shared package, and migrate to `0002`. Keep local data intact.

Configure the existing notification queue `telelink-local-notification`, Floci
endpoint `http://localhost:4566`, synthetic sender `notifications@telelink.test`
and frontend URL `http://localhost:5173`. The worker's four distinct owner keys
must match `SERVICE_NOTIFICATION_SECRET` in identity, scheduling, document and
fulfilment. Restart these owner APIs after changing keys. Their direct local URLs
are ports `8001`, `8003`, `8007` and `8006`, without frontend ingress prefixes.

Before sending, verify the synthetic sender and patient mailbox through local SES
`verify_email_identity`. This run used `patient@example.test`. Confirm Floci has
no SMTP forwarding configured; the documented store-only mode captures messages
at `http://localhost:4566/_aws/ses`. Do not configure a real SMTP destination for
this local check.

Keep the existing source outbox publishers running. From `services/notification`,
with the same configuration and dummy local SDK credentials:

```powershell
$env:AWS_ACCESS_KEY_ID='test'
$env:AWS_SECRET_ACCESS_KEY='test'
$env:AWS_DEFAULT_REGION='ap-southeast-1'
python -m app.worker --once
python -m app.worker --once
```

For a continuing local demo, `python -m app.worker` runs the existing worker loop.
Do not reset sent jobs or recreate/publish events to force a result. Stale events
are intentionally acknowledged without a send; rerun a real journey when new
eligible events are needed. Physical delivery, AWS SES, real recipient inboxes,
bounces and exactly-once external delivery remain outside this evidence.

Run the read-only verifier from the repository root with notification's dependencies:

```powershell
services/notification/.venv/Scripts/python.exe tests/e2e/check_i04_journey.py <appointment-id> <prescription-document-id> <delivery-id>
```

Use `--config-root <configured-checkout>` for a separate source checkout. Each
database connection enforces read-only transactions using its service's own role.
The checker performs only owner-context GETs, SQL reads and local SES inspection.
It does not publish events, consume queues, dispatch messages or modify jobs.
Its output verifies persisted state/captures; the observed transport run is below.

## Observed evidence

The source APIs and publishers were the same real processes used for I03. The
notification tables were initially empty; the existing queue held six visible
messages. The first worker process reported
`processed=6 duplicates=0 failed=0 dispatched=3`. A newly started second process
reported `processed=0 duplicates=0 failed=0 dispatched=0`.

| Source event ID | Template | Captured subject |
| --- | --- | --- |
| `85cce573-219c-425c-84e2-af44887f9e28` | booking_confirmed | Your booking is confirmed |
| `f73c9a64-b303-567c-b4cb-d4eb4cdb4bda` | document_ready | Your document is ready |
| `657528a4-5cad-4d93-b470-0d4b58a12f3d` | delivery_updated | Your delivery has an update |

The delivery message corresponds to I03's verified cleanup cancellation. Earlier
pending, unknown and submitted events were stale against current cancelled state,
so they created inbox receipts but no jobs. This does not claim physical delivery.

The twenty persisted-state/capture checks passed: journey links, one published
source event per selected resource/current status, authoritative synthetic patient,
one matching job/inbox entry, `sent` with one attempt, three distinct SES acceptance
IDs, and exact recipient/sender/subject/plain-text/HTML captures. Matching the
existing generic templates excludes clinical notes, medication names, credentials
and signed download URLs. No captured bodies or recipient details are committed.
Substituting an unrelated document ID was rejected; checker reruns created no mail.
All 91 existing notification tests passed against a separate disposable database.

Rerun identifiers: appointment `502824f7-7eb1-4282-bee5-4aa963dd9e1c`, prescription
document `9f91a3a4-dec1-5938-86a2-99447348d88b`, delivery
`fa577d52-1d46-458b-be4b-6ecc7cb5ce8b`.
SES `sent` records provider acceptance only. Historical captures/jobs are retained
for inspection; a later change to ownership, mailbox or template can legitimately
make a current-state verification fail.
