# Notification event worker (N02)

Run the worker separately from the owner-service APIs. It consumes the existing
C05 notification queue, resolves the patient through the resource owner, gets the
current email from identity, and commits the inbox row plus a pending job in one
transaction. Only then does it acknowledge SQS. A separate dispatch step commits
a send claim before calling SES and records the result afterward.

## Setup

Install the pinned dependencies using the notification README, provision the
notification schema and export `SERVICE_DATABASE_URL` before Alembic:

```powershell
python -m alembic upgrade head
python -m app.worker
# One queue batch and up to ten send attempts, then exit:
python -m app.worker --once
```

Migration `0002_notification_worker` adds the inbox, send claims and retry timing.
Existing failed N01 jobs keep `ready_at=NULL`; they are not silently retried.
Downgrading refuses unresolved sending/uncertain jobs. Migration rollback deletes
the inbox; use the documented downgrade only on disposable development data.

Copy `.env.example`, configure the four upstream URLs, and generate four distinct
random keys of at least 32 bytes. For each row, the worker's key must match that
owner service's `SERVICE_NOTIFICATION_SECRET`. Keep them different from existing
billing, consultation, records, access-decision and cursor keys.

| Owner | Worker URL | Worker key | JWT audience |
| --- | --- | --- | --- |
| Identity | `SERVICE_IDENTITY_URL` | `SERVICE_IDENTITY_SECRET` | `telelink-identity-notification` |
| Scheduling | `SERVICE_SCHEDULING_URL` | `SERVICE_SCHEDULING_SECRET` | `telelink-scheduling-notification` |
| Document | `SERVICE_DOCUMENT_URL` | `SERVICE_DOCUMENT_SECRET` | `telelink-document-notification` |
| Fulfilment | `SERVICE_FULFILMENT_URL` | `SERVICE_FULFILMENT_SECRET` | `telelink-fulfilment-notification` |

Restart the four owner APIs after setting their keys. The service-local endpoints
fail closed when the key is absent. The worker sends 60-second JWTs with caller
`notification`, the exact audience above, no redirects and a bounded HTTP timeout.
HTTPS is required outside local/test environments. No other service's tables are
read or written by the notification worker.

The new internal projections are:

- Scheduling: `GET /internal/appointments/{id}/notification-context?tenant_id=...`
- Document: `GET /internal/documents/{id}/notification-context?tenant_id=...`
- Fulfilment: `GET /internal/deliveries/{id}/notification-context?tenant_id=...`
- Identity: `GET /internal/notification-recipients/{patient_id}`

Owner projections return only tenant/resource/patient links, eligibility, and the
source links needed for verification. Identity returns only the patient's ID and
email; it refuses non-patients and missing addresses. Successful projections use
`Cache-Control: no-store`. Notifications validate all returned IDs before sending.
No clinical contents, document object keys, signed URLs or courier contact details
are exposed by these endpoints.

Use F12's existing `telelink-local-notification` queue and its EventBridge routes
for `appointment_confirmed.v1`, `document_ready.v1` (prescription or MC) and
`delivery_status_changed.v1`. No event contract or root Compose changes are needed.
`SERVICE_QUEUE_NAME` can select an isolated queue. Local Floci uses exported dummy
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, a verified synthetic sender and
`SERVICE_AWS_ENDPOINT_URL=http://localhost:4566`. AWS omits endpoint overrides and
uses a task role with SQS receive/delete/get-queue and SES send permission. AWS
queue/SES provisioning and deployment remain W10/W19.

## Sending and recovery

| Status | Meaning and worker behaviour |
| --- | --- |
| `pending` | Committed job, eligible for its first send. |
| `sending` | Claim committed before SES; another dispatcher cannot claim it. |
| `sent` | SES returned an acceptance ID and the database recorded it. No resend. |
| `failed` | Definitive SES rejection. Only explicit throttle rejections receive a bounded retry time. |
| `uncertain` | Acceptance cannot be ruled out. No automatic resend. |

`SERVICE_SEND_MAX_ATTEMPTS` defaults to 3. Throttled attempts wait
`SERVICE_RETRY_SECONDS` (default 60); exhausted/permanent failures keep
`ready_at=NULL`. Hidden SES SDK retries are disabled. Network errors, missing
acceptance IDs, unknown send errors and unknown provider failures become
uncertain. A process crash leaves a sending claim; after `SERVICE_STALE_SECONDS`
(default 300, minimum 60), the next worker marks it uncertain without resending.
A database failure after SES acceptance therefore does not automatically duplicate
an email. Restart the worker after a database outage; no in-memory state is needed.

The shared inbox suppresses repeated event IDs, including after failed SQS
acknowledgements. `FOR UPDATE SKIP LOCKED` plus the committed claim prevents two
senders claiming the same job. Deduplication is per event ID; genuinely distinct
events can create separate emails. SES acceptance is not an inbox delivery receipt,
and this prototype does not implement bounce/complaint tracking or exactly-once
delivery guarantees.

Stale delivery statuses, non-current deliveries and appointments no longer in a
confirmed consultation lifecycle are acknowledged without a job. Missing/invalid
owner context or an unavailable mailbox fails intake, leaving SQS to retry and
then route to its configured DLQ. Those failures have no job yet. Use
[the replay procedure](../../docs/messaging-replay.md) after repairing the source
or configuration; an already committed event remains deduplicated.

Inspect safe status metadata as the notification database operator:

```sql
SELECT job_id, template, status, attempts, error_code, ready_at, send_started_at
FROM notification.jobs ORDER BY created_at;
```

For uncertain jobs, inspect the provider evidence before deciding whether to leave
the job held, record verified acceptance, or deliberately retry it. There is no
automatic reset of uncertain jobs and no public retry endpoint. In local Floci,
match the stored acceptance ID (when available), recipient and subject in
`/_aws/ses`. Treat recipient emails as private data; the worker logs fixed event
names/counters and error types, never raw HTTP/SES errors, mailboxes or bodies.
Worker SDK payload debug logs are suppressed even at `SERVICE_LOG_LEVEL=DEBUG`.
Retention policy and an operator UI remain future work.

## Verification

On 19 October 2026, the isolated PostgreSQL 17 checks passed: notification 91,
identity 124, document 101, fulfilment 325, and scheduling with Redis 233 passed
(two expected skips). Ruff lint and format passed for all modified code.
Notification checks cover concurrent dispatch, duplicate events, SQS delete
failure/replay, lookup rollback, stale events, throttle limits, persistent failures,
process-crash claims and database failure after SES acceptance. Migration checks
cover round-trips, drift, legacy failed jobs and refusal to downgrade ambiguity.
The four owner-service suites include missing/wrong caller/audience credentials,
minimal response fields and tenant/patient restrictions.

Actual local verification used four running owner APIs backed by independently
migrated/seeded service schemas. `python -m app.check_pipeline <synthetic-ids.json>`
created an isolated EventBridge bus/rule/SQS queue, published booking,
prescription-ready, MC-ready and delivery events twice each, and verified four
jobs and four captured emails with exact recipient/subject/text/HTML. Recreating
dispatch sessions produced no extra send. A newly started `app.worker --once`
process then acknowledged four duplicate events with `dispatched=0`. Temporary
messaging resources are removed by the check; captured synthetic emails and jobs
remain for inspection until the isolated verification database is removed.

The pipeline checker permits only host-local APIs and Floci, requires empty
notification tables, and checks recipients end in `@telelink.test` before sending.
Its JSON file supplies `tenant_id`, `appointment_id`, `prescription_id`,
`document_id`, `medical_certificate_id`, `mc_document_id`, `order_id` and
`delivery_id` for matching synthetic rows already present in the owner services.
It does not create bookings, PDFs, payments or deliveries. This verifies N02's
notification integration, not the full I04 journey or deployed AWS email delivery.
