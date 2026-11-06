# Background jobs and operational recovery

Reusable Terraform module for three VPC-attached document/notification Lambdas,
queue mappings, scheduled durable dispatch and alarms. The platform composes it
with existing queues/network/storage. Use the [active demo](../../envs/demo/README.md)
or [managed reference](../../examples/sg-managed/README.md) for complete deployment.
The following module integration instructions were consolidated from RF27; example
concurrency values are not the platform singleton defaults.

## Runtime and local behavior

| Workload | AWS entrypoint | Trigger |
| --- | --- | --- |
| Document PDF generation | `app.lambda_handler.handler` in the document image | Existing document SQS queue |
| Notification intake | `app.lambda_handler.intake` in the notification image | Existing notification SQS queue |
| Notification dispatch/recovery | `app.lambda_handler.dispatch` in the notification image | EventBridge Scheduler, once per minute |

Lambda processes the existing EventBridge-in-SQS envelope through the same
`handle_event` transaction as local workers. A successful response acknowledges a
message only after its inbox and domain effects commit. Failed records return
`batchItemFailures`; duplicate events acknowledge without repeating the effect.
Generation retains private S3 verification, immutable PDF recovery, audited source
projections and document-ready outbox staging. Existing supported events generate
prescription and medical-certificate PDFs; receipt support was subsequently added by RF33/RF51; see [patient emails](../../../docs/patient-emails.md).

Notification intake acknowledges after saving a durable job, not after SES delivery.
The separate scheduled dispatcher processes at most 20 jobs per invocation, leaves
time for shutdown, retries due definitive failures and recovers stale sends into
`uncertain`. It does not automatically resend ambiguous SES outcomes. This schedule
is required even when the queue is empty. Definitively exhausted/uncertain jobs
still require the existing operator review; queue/DLQ alarms alone do not measure
the entire email-job lifecycle. One minute plus backlog is an intentional email
dispatch delay, not a real-time notification guarantee.

No Compose commands, existing Dockerfiles, queue contracts or database schemas
change. Existing local polling workers continue to run. All other workers,
including the five outbox publishers, retain their current runtime.

## Build the two Lambda images

From the repository root, using Docker Buildx:

```powershell
docker buildx build --platform linux/amd64 --provenance=false --build-context python_common=packages/python_common -f services/document/Dockerfile.lambda -t telelink-document-lambda:rf26 --load .
docker buildx build --platform linux/amd64 --provenance=false --build-context python_common=packages/python_common -f services/notification/Dockerfile.lambda -t telelink-notification-lambda:rf26 --load .
```

Push to the existing ECR repositories with the environment's deployment tooling,
then supply immutable `repository@sha256:...` URIs. Both notification functions use
the same image with different command overrides. The Lambda images use Python 3.12
and existing dependency locks; the API/local worker images remain unchanged.
The ECR repository policy must permit Lambda image retrieval; its owner/deployment
role must configure this before creation. This module does not replace W03's
repository policies.

## Worker module wiring

`background-jobs` creates three VPC-attached Lambda functions, their
scoped roles/log groups, two SQS event source mappings, the notification
schedule, a dispatch-failure queue, alarms and async dispatch failure routing.
It accepts existing resources rather than recreating W02/W06/W08-W10 infrastructure.
The demo platform already wires this module. Direct consumers must supply the
required resources and coordinate their owning root.

Required inputs:

- `name_prefix`, `environment`, private `subnet_ids`, `security_group_ids`.
- `workers`: exactly `document`, `notification-intake`, `notification-dispatch`.
  Each supplies `image_uri`, `config_secret_arn`, `concurrency`, `timeout_seconds`,
  optional `memory_mb`, public `environment` settings and any required `kms_key_arns`.
- `consumer_queues`: exactly `document` and `notification-intake`. Pass `arn`,
  `visibility_timeout_seconds` and `redrive_policy` directly from the queue-owning
  Terraform resources/module outputs, plus the matching `dlq_arn`. Do not invent
  values disconnected from the real resources. The module rejects missing/mismatched
  redrive and visibility shorter than six times the function timeout.
- `document_bucket_arn`, verified `ses_identity_arn`, `alarm_action_arns` (confirmed
  SNS topics), and `monitored_queues` keyed by actual AWS queue name with `is_dlq`
  and optional `max_age_seconds`. Include every consumer queue, consumer DLQ and
  EventBridge delivery DLQ. The dispatch DLQ is monitored automatically.

Start with document concurrency 5/timeout 120 seconds and notification intake and
dispatch concurrency 2/timeout 60 seconds. These are example budgets, not measured
capacity claims. Queue visibility must therefore be at least 720/360 seconds.
Batch size is one and queue maximum concurrency equals function reserved concurrency.
RDS connection budgeting must include all API replicas and other workers. Lambda
uses SQLAlchemy `NullPool`: sessions return connections immediately, and frozen
environments do not retain idle pools. Upstream services also use connections, so
these limits are not a global database connection cap.

Secrets Manager stores JSON using Settings field names, without the `SERVICE_`
prefix. Supply `database_url` and service-specific credentials there. Document
generation needs `records_url`, `records_secret`, `document_bucket`; notifications
need `email_sender`, `app_url`, `identity_url`, `scheduling_url`, `document_url`,
`fulfilment_url` and their distinct service secrets. Public URLs/settings may be
passed through `workers[*].environment` as `SERVICE_*` strings. Secret JSON values
override these; do not put credentials in Terraform variables or state. Each
invocation reads the secret so rotation does not rely on recycling warm containers.
AWS provides the execution credentials. No emulator override is accepted by the
module. Use `environment=development`, `demo` or `production`.

Private networking must permit RDS and the required HTTPS service projections.
Provide NAT or suitable endpoints for Secrets Manager, S3, SES and SQS as applicable.
Function VPC security groups must be admitted by RDS and service ingress groups.
Customer-managed encryption keys need matching key policies as well as the supplied
IAM decrypt permissions. The module never creates a second set of domain tables.


## Monitoring and recovery

Set `SERVICE_OUTBOX_METRICS=true` and the correct `SERVICE_ENVIRONMENT` on all five
ECS outbox publishers. Every running process emits raw CloudWatch Embedded Metric
Format JSON at most once per minute, including empty-queue zeros. Configure the
ECS `awslogs` driver/CloudWatch Logs ingestion so EMF is extracted. Metrics use
namespace `TeleLink/Outbox`, dimensions `Service` (owning schema) and `Environment`:

- `PendingEvents`: all unpublished rows, including events waiting for retry.
- `OldestPendingAge`: seconds since the oldest pending event was created.

The module alarms on oldest outbox age over 300 seconds for two periods; missing
publisher metrics also alarm. Queue age defaults to 300 seconds, DLQ visible count
alarms above zero, and Lambda execution errors alarm above zero. Set real action
topic ARNs and confirm subscriptions; an empty action list creates silent alarms.
If multiple publisher replicas run, the same dimensions aggregate them: one live
publisher is enough to provide backlog visibility.

Investigate source service state -> outbox -> EventBridge delivery DLQ -> consumer
queue/inbox -> owning worker logs. Fix the cause before replaying DLQ messages.
Use the existing replay procedure and original event IDs; do not delete inbox rows
to force duplicate business effects. A queue backlog is waiting work, not an excuse
to raise concurrency beyond the database/provider budget.

## Cutover and verification gates

1. Build/test images, finish infrastructure dependencies and apply the owning queue
   visibility/redrive settings. Verify IAM, network reachability and secret fields.
2. Stop/drain the existing document consumer and combined notification worker before
   enabling their Lambda consumers/schedule. Leave outbox publishers running. Shared
   inboxes and durable jobs support safe redelivery; no data migration is required.
3. Verify one real prescription/MC -> private S3 PDF -> document-ready event ->
   notification job -> SES acceptance. Verify access checks on the unchanged API.
4. Exercise duplicates, poison messages/DLQ, provider failures, dispatch with no new
   queue messages, stale/uncertain send recovery, alarms and a synthetic backlog
   while observing actual Lambda concurrency/RDS connections.
5. Verify CloudFront miss then hit, distinct cursor pages, authenticated create
   through the shared path, uncached protected reads/writes and unchanged API errors.
6. To roll back, disable mappings/schedule and let invocations finish before starting
   the existing ECS consumers. Preserve queues, inboxes, jobs, outboxes and private
   objects. Restore disabled caching or invalidate paths if needed.

Local evidence is recorded in the PR. Terraform mocked plan tests validate wiring
and safeguards; they do not establish deployed AWS behavior. PostgreSQL suites and
image builds run in CI. Historical AWS rollout is recorded under RF32/RF51 in the backlog. A new rollout
still needs its own cutover, IAM, provider and concurrency verification.
