# U17 medical certificates

The assigned doctor can select **Issue MC** in the booked consultation's note
workspace, enter a Singapore calendar start date, positive whole-number duration
and optional additional notes, and save/reload that draft. The inclusive end date
is `start date + duration - 1`; a one-day MC ends on its start date. Additional MC
notes are distinct from private clinical notes. Only saved draft values are issued;
the form explicitly flags unsaved changes. MC is off by default.

## Ownership and completion contract

Clinical records owns `medical_certificates`, one row per appointment. Draft writes
require the assigned doctor, current active clinic membership, matching appointment
context and scheduling status `in_progress`. Patients cannot read unissued drafts;
administrative roles and unrelated participants cannot issue MCs.

`GET/PUT /api/v1/clinical-records/appointments/{id}/medical-certificate` reads/saves
the draft. Server-owned fields and nonintegral, nonpositive or overflowing date
periods are rejected. The response exposes the calculated `end_date`, `issued_at`
and `finalized_at`. MC reads have durable access audits and `Cache-Control: no-store`.

Consultation's existing authenticated `POST /appointments/{id}/complete` ends its
local session, waits for scheduling to accept completion, then calls
`POST /api/v1/clinical-records/internal/appointments/{id}/complete-mc` using the
scoped `consultation` service credential, audience `telelink-records-consultation`.
The body contains the four context IDs, the authoritative session `completed_at`
and `consultation_date` derived from the actual session start in Asia/Singapore.
Browsers cannot call this service-only handoff or attest completion themselves.

Clinical records serializes draft writes and finalization on the appointment,
checks the full context, and seals the decision once. Selected drafts get one
issued timestamp and `medical_certificate_issued.v1` event in the same transaction.
Absent/disabled drafts are sealed without an issuance event. A database trigger
prevents changes to a sealed decision. Completion retries preserve the original
timestamps and event ID; conflicting completion context is rejected.

The local end, scheduling transition and records handoff are separate transactions.
An uncertain/failed handoff returns an error; the appointment may already be ended
and room admission denied. The completed doctor page checks whether the MC decision
is finalized and exposes **Retry completion handoff** when it is still unconfirmed.
Retry the same consultation completion action. There is no automatic background
reconciler in this prototype. Leaving video or closing a preview does not issue an MC.

## PDF generation and downloads

Run clinical records' existing `python -m app.publish_events` and document's
`python -m app.worker` processes. The document route accepts both prescription and
MC issuance events. MC events contain only IDs. The worker retrieves
`GET /api/v1/clinical-records/internal/medical-certificates/{id}/document` using the
existing document credential, exact tenant/appointment query and
`purpose=medical_certificate_pdf`. It refuses unissued or mismatched sources and
obtains current patient/doctor/clinic names through the owning identity/tenant APIs.
Service projection reads are durably audited; private clinical notes are excluded.

The existing P01 MC template renders the trusted names, consultation date, MC
start/end dates, inclusive duration and escaped additional notes. Identity and
tenant currently do not own registration/address fields, so those unavailable
fields are omitted; no browser-supplied or fabricated profile details are used.
The bundled font still rejects unsupported glyphs explicitly, as in P01/P02.

The document ID, private object key and ready-event ID are deterministic per MC.
The worker persists a `pending` document independently of the inbox transaction,
then atomically commits ready metadata, inbox acknowledgement and a ready outbox
event after successful storage. A processing failure persists `failed`, rolls back
inbox acknowledgement and leaves the SQS message retryable. An uploaded object is
verified and reused after a lost response/database commit, without regenerating it.
Source text, profile responses, object keys and credentials are excluded from logs.

P03/U14 already support `medical_certificate_pdf`: patient and current assigned
active doctor see preparation/failure states and can request a fresh signed
download only after storage succeeds. Other users and revoked doctors are denied;
download access intents are durably audited. If a PDF remains failed after queue
retries, the clinic/operator should fix the source/configuration and use the
[existing DLQ replay procedure](messaging-replay.md), preserving the original event.
Replay also works when an uploaded object survived the failed attempt.

## Setup

1. Apply clinical records migration `0005`: `python -m alembic upgrade head` from
   `services/clinical_records` with its own `SERVICE_DATABASE_URL`. Existing
   prescription audit rows are preserved. Document and consultation need no new
   database migration.
2. Configure consultation `SERVICE_RECORDS_URL` to the clinical-records base,
   e.g. `http://127.0.0.1:8005/api/v1/clinical-records` locally. Set consultation
   `SERVICE_RECORDS_SECRET` equal to records `SERVICE_CONSULTATION_SECRET`, an
   independent random secret of at least 32 bytes, distinct from all existing keys.
   These are required for completion; readiness checks reject absent configuration.
3. Keep records' existing `SERVICE_DOCUMENT_SECRET`, identity/tenant document
   secrets and upstream URLs configured for the issued source projection. Keep
   document's existing records URL/secret, private bucket, queue, browser endpoint
   and scheduling/identity settings. See the service `.env.example` files and
   [document worker setup](../services/document/docs/worker.md).
4. Reapply the existing F12 event bootstrap so the document rule uses the updated
   `dev/floci/patterns/document.json`. Existing deployed rules must likewise add the
   MC source/type pair. No queue or root Compose change is required.
5. Restart APIs, publisher and worker after changing configuration. Protect all
   `/internal` routes at deployed ingress. The existing Vite proxy blocks them.

## Verification

Focused automated checks cover inclusive one-day, month-boundary and leap-day
periods; invalid/server-owned input; unrelated patient/doctor/clinic/admin access;
no-MC completion; parallel completion and event deduplication; transactional
rollback; service-only projection/audits; private notes exclusion; failed source,
upload and lost upload response; commit recovery and concurrent generation.

Local verification on 19 October 2026:

- 133 clinical-records, 111 consultation and 95 document PostgreSQL/PDF tests;
  114 frontend tests, ESLint and production typecheck/build; shared event checks
  (93 passed, 12 optional database-dependent tests skipped).
- Real identity, tenant, scheduling, billing, consultation, clinical-records and
  document apps, each using its own PostgreSQL role/schema. Two isolated Chromium
  contexts over local HTTPS verified MC entry, month-boundary preview, save/reload,
  private note save, authoritative completion and patient/doctor PDF downloads.
- Real Floci EventBridge/SQS/S3 routing and storage: one issued event, deliberate
  source outage persisted a failed document and denied premature download, browser
  displayed failure, replay stored the PDF, same/distinct event duplicates reused
  one object, the MC-ready event reached the notification queue, and both participants
  downloaded actual PDF bytes. PDF text included
  only MC additional notes; the private consultation note was absent.
- A real no-MC completion produced no document. Repeated completion preserved the
  issued MC. An unrelated user was denied record access; revoking the assigned
  doctor's membership denied download access.

Fixtures used synthetic persisted paid bookings, signed test identities and a
local TLS certificate exception. Login/hosted payment were not part of this check;
fulfilment was absent, so prescription catalogue/save operations were not exercised
in the browser run. Existing prescription regression tests passed. Emulator results
do not establish real AWS IAM, private-bucket or URL expiry enforcement. Deployment,
cross-network/physical-device video and full prescription journeys remain in their
existing tasks. U17 completed in merged PR #204; issue #152 is closed and the
matching backlog task is checked off.
