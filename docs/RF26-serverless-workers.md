# RF26: Lambda application adapters and operational metrics

Tracks issue #314 / PR #315. Terraform modules, CloudFront rules, Lambda concurrency
mappings, schedules and alarms are split into RF27 / issue #316 at the user's
request. This application change does not deploy AWS resources.

## Runtime entrypoints

| Workload | Lambda entrypoint | Required trigger |
| --- | --- | --- |
| Document PDF generation | `app.lambda_handler.handler` in the document image | Existing document SQS queue |
| Notification intake | `app.lambda_handler.intake` in the notification image | Existing notification SQS queue |
| Notification dispatch/recovery | `app.lambda_handler.dispatch` in the notification image | Schedule, proposed once per minute |

SQS handlers use the existing transactional inbox and domain operations. Success
acknowledges committed work; failed records return `batchItemFailures`, and duplicate
events do not repeat effects. PDF generation retains private S3 verification,
immutable-object recovery, audited source reads and document-ready outbox staging.
Existing supported events generate prescription and MC PDFs; receipt events are
not added.

Notification intake commits a durable job before acknowledging. Scheduled dispatch
is required even with no new messages: each invocation processes at most 20 jobs,
stops starting sends near timeout, retries eligible definitive failures and recovers
stale sends into `uncertain`. Ambiguous SES outcomes are not automatically resent.
Exhausted/uncertain jobs retain the existing operator-review procedure. A schedule
introduces dispatch delay; this is not a real-time email guarantee.

Lambda uses SQLAlchemy `NullPool` and closes database/HTTP/AWS clients. Frozen
instances do not retain idle connection pools. External concurrency caps must still
budget for APIs and other workers. Deployment needs `ReportBatchItemFailures` and
safe visibility/concurrency settings; RF27 supplies that infrastructure.

## Packaging and settings

Build from the repository root:

```powershell
docker buildx build --platform linux/amd64 --provenance=false --build-context python_common=packages/python_common -f services/document/Dockerfile.lambda -t telelink-document-lambda:rf26 --load .
docker buildx build --platform linux/amd64 --provenance=false --build-context python_common=packages/python_common -f services/notification/Dockerfile.lambda -t telelink-notification-lambda:rf26 --load .
```

Lambda images use Python 3.12 and existing dependency locks. Both notification
functions use one image with different command overrides. CI builds both images.
Existing Dockerfiles, Compose workers and database schemas remain unchanged.
Outbox publishers and other workers retain their current runtime.

`SERVICE_CONFIG_SECRET_ARN` identifies Secrets Manager JSON using Settings field
names without the `SERVICE_` prefix. Each invocation reads it; values override
public `SERVICE_*` settings without modifying the process environment. Store the
`database_url` and distinct service credentials there, not in Terraform state.
Document generation needs `records_url`, `records_secret` and `document_bucket`.
Notifications need `email_sender`, `app_url`, identity/scheduling/document/fulfilment
URLs and their service secrets. AWS supplies execution credentials. Existing
configuration, HTTPS and access-validation rules remain in force.

## Cache headers and metrics

Successful public clinic listings and by-slug profiles return
`Cache-Control: public, max-age=0, s-maxage=60, must-revalidate`; other tenant
responses default to `no-store`. Public responses are viewer-independent. These
headers allow shared caching for 60 seconds; actual CloudFront rules belong to
RF27 and are not activated by this PR. Booking, payment and permission decisions
continue to use authoritative state.

Set `SERVICE_OUTBOX_METRICS=true` and `SERVICE_ENVIRONMENT` on each ECS publisher
to emit CloudWatch Embedded Metric Format JSON at most once per minute. Configure
CloudWatch Logs ingestion to extract namespace `TeleLink/Outbox`, dimensions
`Service` (owning schema) and `Environment`. `PendingEvents` counts all unpublished
events, including delayed retries; `OldestPendingAge` measures the oldest pending
event in seconds. Empty outboxes emit zeros. No payload/patient data is logged.
RF27 supplies alarms. Emission is opt-in and needs no CloudWatch API permissions.

## Verification and activation

Local shared tests: 118 passed/12 PostgreSQL skips; notification 65/29; document
45/61; tenant 7/125. Ruff passed. All 34 CI checks on the original `fd8f05d` revision
passed, including PostgreSQL suites and both Lambda builds. PR #315 records checks
for the application-only revision separately.

No local runtime switch or data migration is needed. AWS activation must finish
infrastructure prerequisites, configure safe queue/concurrency settings, stop/drain
the corresponding ECS consumers, then enable Lambda mappings and the dispatch
schedule. Leave outbox publishers running. Verify real private PDFs, email jobs,
SES acceptance, duplicates, failed-message replay, durable retries and access checks.
For rollback, disable triggers and let invocations finish before restarting ECS
consumers; preserve jobs, queues, inboxes, outboxes and S3 objects. Real AWS behavior
remains a deployment gate, distinct from merging these application adapters.
