# P02 prescription PDF worker

## Flow and boundaries

R03 commits an issued prescription and an IDs-only event. The document worker
consumes `prescription_issued.v1` from its own queue using M03. It retrieves the
issued prescription through the C04 private records endpoint, renders P01's
prescription template and stores one PDF in a private S3 bucket. Document metadata,
the M03 inbox row and a `document_ready.v1` outbox entry commit together. SQS is
acknowledged only after that transaction commits. A separate M02 publisher sends
the ready event to notification. Clinical payloads do not enter either event.

There is no new issuance snapshot. Patient/doctor/clinic names are fetched from
identity/tenant APIs during initial generation. The first successfully uploaded
PDF is retained even if profile details later change. Existing issued medication
content remains frozen by clinical records. The source models do not contain a
clinic address or doctor registration number, so those prescription header fields
are optional and omitted. Their authoritative storage/maintenance is follow-up
work; receipt and MC template requirements remain unchanged. Existing font coverage
limitations, including unsupported CJK names, still apply.

P03 owns authorised document list/download APIs and browser-reachable signed URLs;
U14 owns their UI. This worker does not expose bucket/key details to browsers or
claim a complete payment/consultation/PDF download journey.

## Configure and migrate

From `services/document`, install `requirements.lock.txt` and the editable shared
package as described in the main README. The lock now includes boto3 and its
dependencies. Export `SERVICE_DATABASE_URL` and upgrade document to `0002`.
Upgrade clinical records to `0004` before deploying its HTTP process; readiness
expects that revision. Identity and tenant need code/config updates, with no new
migrations. Downgrades remove the new service read audit or inbox/outbox history;
use only a disposable environment or reconcile queued work first.

Configure three independent random keys of at least 32 bytes:

| Connection         | Caller setting                             | Receiver setting                  | JWT audience                 |
| ------------------ | ------------------------------------------ | --------------------------------- | ---------------------------- |
| document → records | document `SERVICE_RECORDS_SECRET`          | records `SERVICE_DOCUMENT_SECRET` | `telelink-records-document`  |
| records → identity | records `SERVICE_IDENTITY_DOCUMENT_SECRET` | identity `SERVICE_RECORDS_SECRET` | `telelink-identity-document` |
| records → tenant   | records `SERVICE_TENANT_DOCUMENT_SECRET`   | tenant `SERVICE_RECORDS_SECRET`   | `telelink-tenant-document`   |

Keys must differ from each other and existing cursor/service keys. Supply real
secrets through environment/secret injection; do not commit them. Credentials are
HS256 purpose-specific JWTs, issued for 60 seconds and accepted for at most five
minutes, matching the repository's existing prototype service-auth approach.
User Cognito credentials and other service/purpose credentials cannot invoke
these operations. Production upstream URLs require HTTPS.

The new internal APIs are:

- Records: GET `/api/v1/clinical-records/internal/prescriptions/{id}/document`,
  with `tenant_id`, `appointment_id`, `purpose=prescription_pdf`. Only document
  callers; source links must match and status must be issued. A durable
  `service_read_audits` row is required before returning clinical content.
- Identity: GET `/internal/document-participants`, with `patient_id`, `doctor_id`.
  Only records callers; returns those IDs and names, excluding email/roles.
- Tenant: GET `/internal/clinics/{tenant_id}/document-profile`. Only records
  callers; returns ID/name even for inactive clinics so historical issued
  prescriptions remain generatable.

Records supplies participant/tenant IDs from its own persisted prescription.
Each service reads only its own database. Vite excludes internal identity/tenant
routes as well as records/fulfilment routes, including encoded internal segments.
AWS ingress must exclude these routes too; private networking alone is not auth.

Set document `SERVICE_RECORDS_URL` to the records API prefix (direct local:
`http://127.0.0.1:8005/api/v1/clinical-records`). Records identity/tenant URLs point
to their direct bases, normally ports 8001/8002. Document also needs:

```dotenv
SERVICE_DOCUMENT_BUCKET=telelink-local-documents
SERVICE_DOCUMENT_QUEUE_NAME=telelink-local-document
SERVICE_EVENT_BUS_NAME=telelink-local
SERVICE_AWS_REGION=ap-southeast-1
# Local only; omit for AWS task-role access.
SERVICE_AWS_ENDPOINT_URL=http://localhost:4566
```

Use dummy SDK credentials for Floci; AWS uses the task role. F11/F12 bootstrap
already defines the local bucket and document queue/rule/DLQs. Keep all four S3
public-access-block flags enabled. The worker fails closed if it cannot verify
them. It sets no public ACL, requests AES256 encryption and uses conditional
`IfNoneMatch=*` uploads. Runtime permissions are S3 GetBucketPublicAccessBlock,
GetObject/PutObject in the prescription prefix, SQS GetQueueUrl/ReceiveMessage/
DeleteMessage and EventBridge PutEvents for the publisher. Scope each role to its
own resources; runtime does not need bucket administration or object deletion.

Run two processes from `services/document`:

```powershell
.venv/Scripts/python -m app.worker
.venv/Scripts/python -m app.publish_events
```

`--once` consumes one message without long polling or publishes one due outbox
batch, respectively. Continuous consumption receives one message at a time and
polls for five seconds to stay below the shared SDK's read timeout. Set queue
visibility above the observed worst-case fetch/render/upload/commit duration
(120 seconds is the local check setting); retain bounded receives and a DLQ.

## Retry and recovery

A prescription-scoped PostgreSQL transaction lock serializes distinct events for
the same prescription. Metadata uniqueness and a stable document ID provide one
logical document. Objects use `prescriptions/{tenant_id}/{prescription_id}.pdf`;
keys are internal identifiers, not download authorisation.

Before fetching/rendering, the worker checks for an existing object. A previously
uploaded PDF is accepted only after validating its PDF/content type, length,
SHA-256 and matching document/prescription/tenant/appointment metadata. It restores
patient/doctor ownership from the worker-written object metadata. If upload
succeeds but acknowledgement or database commit fails, the next delivery reuses
that exact object. A conditional upload collision also reuses the original object;
an integrity/context mismatch fails closed. Do not grant unrelated writers access
to this prefix or edit its recovery metadata.

Existing pending/failed metadata rows are reused. Ready rows and inbox duplicates
do not trigger another lookup, render, upload or ready event. Before any successful
upload, failures can cause rendering to be retried; the guarantee is one logical
stored artifact, not exactly one execution of rendering code.

Lookup, rendering, storage and commit failures leave processing unacknowledged.
Incomplete work does not become ready. Exceptions from clinical validation and
provider calls are sanitised before the shared consumer logs them. Diagnose DLQs
using metadata, fix the cause, then replay the original event using
[the M04 runbook](../../../docs/messaging-replay.md). Do not replace event IDs to
force regeneration, overwrite a PDF, or delete an uploaded object during recovery.
Receipt/MC generation and notification sending remain separate tasks.

## Verification - 16 October 2026

52 document PostgreSQL/PDF/storage/adapter checks passed, including fresh/repeated
migration, schema parity/isolation, downgrade/re-upgrade, six concurrent distinct
events, same-event replay, failed-row reuse, conditional upload collision, wrong
tenant replay, source/storage failure, upload-accepted timeout and failed-commit
recovery. Recovery retained the original PDF and worked with source lookup disabled.
Failed handlers did not acknowledge or expose clinical error text. All 108 records,
112 identity, 115 tenant and 10 service-JWT tests passed. Frontend's 74 tests,
ESLint, TypeScript/production build, Python lint/format and dependency checks passed.

A local walkthrough used real Floci PKCE/JWKS, identity, tenant, scheduling,
fulfilment catalogue, records, PostgreSQL, EventBridge, SQS and S3. One disposable
in-progress scheduling row was setup only; no payment/consultation integration is
claimed. R03 published the actual committed issuance event. A simulated pre-commit
failure left an uploaded PDF but no ready metadata/inbox acknowledgement. Redelivery
recovered the exact file without a records lookup, persisted one ready document,
deduplicated replay, and published an IDs-only ready event to the notification
queue. A records service-read audit persisted. Encoded internal paths were rejected
by Vite. Synthetic rows, cloud resources, memberships and tokens were cleaned up.

All four bucket public-access blocks were verified and uploads requested private
default ACLs, conditional creation and AES256 encryption. **Floci still returned
200 for an unsigned object read**, the previously accepted emulator limitation in
[issue #54](https://github.com/NorbertLoh/CS5224-Team-39/issues/54) and
[the F16 report](../../../docs/floci-verification.md). These checks establish local
transport/recovery and requested security configuration, not real AWS privacy
enforcement. AWS unsigned-read denial, IAM/encryption/conditional-write behavior
and authorised signed downloads remain deployment/P03 verification. Browser/PDF
download UI is not included.
