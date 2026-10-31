# RF27: Singapore demo deployment, cost and scalability

Issue #316 / draft PR #317. Requested 1 November 2026. These files configure AWS;
they have not been applied and do not prove the AWS patient journey works.

## What is configured

The reusable `infra/modules/demo-platform` composes the existing worker and public
edge modules. `infra/examples/sg-demo` demonstrates its inputs without modifying
Chronoxy's open W01 PR #233 (`infra/bootstrap`, `infra/envs/*`, existing cost docs
and infrastructure README). Wire the module into that agreed state/environment
after coordinating W01; do not apply two roots managing the same resources.

The demo uses `ap-southeast-1` exclusively. Route53 DNS ownership is an input;
ACM is requested and DNS-validated there unless an existing certificate is supplied.
No database credentials, provider keys or
service secrets are generated into Terraform state.

| Component | Demo configuration | Why this choice |
| --- | --- | --- |
| Business APIs | Eight independent ECS Fargate services; one 0.25-vCPU ARM task each | Preserve deployable service boundaries with small resource requests |
| Existing background loops | Containers beside their owning API | Avoid another always-on task for every polling process |
| Scheduling/billing/fulfilment memory | 1 GiB per task | Multiple Python processes need more headroom than a bare API |
| Other APIs and signalling | 0.5 GiB each; one signalling task | Smallest Fargate memory at 0.25 vCPU; no signalling scale-out |
| PDFs/email | Three on-demand Lambda functions; reserved concurrency **one each** | No paid warm capacity; bounded work |
| SQS for those Lambdas | FIFO, batch one, one producer group | Serial processing without the SQS maximum-concurrency minimum of two |
| Database | One `db.t4g.micro`, PostgreSQL 17, encrypted 20-GiB gp3, one-day backup retention | Small Graviton instance; no Multi-AZ standby, replicas or storage auto-growth |
| Redis | 64-MiB localhost scheduling sidecar by default | Holds are a best-effort mirror; PostgreSQL remains authoritative |
| Managed Redis alternative | One TLS `cache.t4g.micro`, no replica/failover | Available via `redis_mode=managed`, with extra hourly cost |
| Outbound access and TURN | One `t4g.nano` ARM utility instance, encrypted 8-GiB disk, one EIP | NAT and coturn share one small host; standard CPU credits avoid EC2 surplus-credit charges |
| Managed egress alternative | One NAT gateway | Less host maintenance, but extra hourly/per-GB cost; never one per AZ |
| Ingress | One shared ALB for HTTP integration and signalling; API Gateway HTTP API | Avoid two ALBs; API services still verify tokens/tenant roles |
| Frontend/files | Private S3 + CloudFront; separate private documents/logo buckets | Static delivery and short-lived authorized PDF URLs |
| Authentication | Cognito public SPA client, PKCE/password flow, verified email | Existing application login integration; no client secret |
| Messaging/email | EventBridge, four consumer queues/DLQs, delivery DLQ, SES sender | Existing event contracts and retries |
| Operations | Three-day logs, queue/outbox/Lambda/DB alarms, account-wide budget alerts | Show observability without high-volume telemetry services |

There are **nine Fargate tasks total**, one per API/signalling workload, not one
task for the entire application. Each owns one API plus its existing workers.
This is a demo cost compromise: worker and API scaling are coupled. It does not
claim independent worker autoscaling or measured capacity at these sizes.

## Hard limits and the scaling demonstration

The example fixes `max_tasks=1` and `allow_scale_out=false`. ECS CPU target-tracking
policies are configured, but min/max are one; they cannot add replicas. Deployments
use `minimum_healthy_percent=0`, `maximum_percent=100`, so replacing a task stops
the old one before starting another. Expect brief deployment downtime.

Raising the generic module's maximum requires explicit `allow_scale_out=true`.
Fulfilment and consultation remain capped at one even then: courier provider
quotas/recovery and live consultation scaling need separate verification.
Signalling always has exactly one task. PostgreSQL/Redis have no read replicas or
automatic failover. The NAT/TURN host is also a deliberate single point of failure.

Lambda document and notification intake use **FIFO with the same fixed message
group on every producer event**, one item per invocation and reserved concurrency
one. The module omits `scaling_config` at one because AWS only accepts a maximum
of two or higher there. This avoids relying on repeated Lambda throttling to
serialize standard queues. Inbox idempotency still matters; FIFO deduplication
does not replace it. A failed item blocks later work in its group until retry/DLQ.
Do not add more message groups without revisiting limits and processing semantics.
The bounded dispatcher is a separate scheduled function, also capped at one.
[AWS SQS/Lambda scaling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html).

Show scalability by explaining: stateless APIs behind target groups; CPU policies
with a budget-limited maximum; queues buffering bursts; one-event Lambda workers;
S3/CloudFront static delivery; database ownership and connection alarms. You can
show a queue backlog draining serially without paying for a live scale-out test.
Do not present this as proof of multi-replica video, high availability or load capacity.

ALB requires two AZ subnets, and RDS requires a DB subnet group spanning two AZs.
Therefore two public/two private subnets exist. All ECS tasks, the database primary
and the utility host are placed in AZ zero; no second compute replica or RDS
standby is created. The load balancer itself necessarily spans two AZs.
[ALB requirements](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html),
[RDS subnet requirements](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.html).

## Cost estimate and avoiding idle charges

List-price inputs were retrieved on 1 November 2026 from AWS's Singapore price
lists; the small snapshot and SKU/source identifiers are in
`infra/examples/sg-demo/cost-assumptions.json`. Values are USD, before tax/credits.
This is a planning calculation, not a bill or a free-tier eligibility claim.

| Baseline | Calculation | Approximate 730-hour month |
| --- | --- | ---: |
| Fargate ARM | 2.25 total vCPU x $0.04045 + 6 total GiB x $0.00442 per hour | $85.80 |
| Single-AZ PostgreSQL compute | $0.025/hour | $18.25 |
| PostgreSQL 20-GiB gp3 | $0.138/GiB-month | $2.76 |
| One ALB, before LCUs | $0.0252/hour | $18.40 |
| Shared `t4g.nano` utility host | $0.0053/hour | $3.87 |
| Public IPv4, assumed minimum three | Two ALB addresses + utility EIP, $0.005/address-hour | $10.95 |
| **Subtotal above** | Excludes the items below | **$140.03** |

Sources: [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/),
[Singapore ECS list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ap-southeast-1/index.json),
[Singapore RDS list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-southeast-1/index.json),
[Singapore ELB list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSELB/current/ap-southeast-1/index.json),
[EC2 on-demand](https://aws.amazon.com/ec2/pricing/on-demand/),
[public IPv4 pricing](https://aws.amazon.com/vpc/pricing/).

Allow extra for the utility disk, 12 Secrets Manager secrets including the RDS
master secret, S3/ECR storage, logs/alarms, ALB LCUs, API Gateway, Lambda/SQS/events,
SES, DNS and traffic. Extra ALB addresses, cross-AZ traffic, TURN internet egress
and RDS surplus CPU credits can increase the bill. A rough low-traffic planning
allowance is **$150-175/month if left running continuously**, not a guaranteed cap.
The optional managed Redis node adds about $17.52/month at $0.024/hour; the sidecar
avoids that baseline. Managed NAT is a separate charge, excluded from this default.

**A short demo followed by teardown is the main saving.** The listed baseline is
about $0.192/hour, around $1.54 for eight hours before the excluded costs. Merely
setting `enable_workloads=false` removes ECS services/Lambdas but keeps RDS, ALB,
utility/EIP and storage billing. Stopping a database/instance is not full teardown.
Do not buy Reserved Instances or Savings Plans for a temporary assignment.

The default $100 budget is an account-wide warning threshold, deliberately below
a full month of this platform. It includes other team spending and sends actual
cost alerts at 50/80/100%; confirm the email subscription. Budgets and task limits
are **not a hard dollar cap**: requests, storage and network traffic can still bill,
and cost data/alerts arrive with delay. Set a lower amount for a one-day demo if
desired and destroy immediately after the demonstration. Keep remote state and
its small storage cost separate from workload teardown.

## Prepare, migrate and run

1. Complete W01's agreed remote-state setup. The standalone example uses local
   state for isolated review; never commit state or run competing roots. Have an
   owned DNS zone; the module requests a free public ACM certificate there or accepts
   your existing Singapore certificate for `origin_hostname`.
2. Copy the example tfvars into an ignored operator file, set the expected account,
   email/domain values and leave `images={}`, `enable_workloads=false`. Run fmt,
   init and an actual account-specific plan for review. No apply has been performed
   by this task. A future foundation apply immediately starts billable infrastructure.
3. Publish normal service images (including notification migration image),
   signalling and Redis to the emitted ECR repositories for **linux/arm64**. Build
   the two RF26 Lambda images for **linux/amd64**. Pin their digests in `images`.
   Do not pass a Lambda image where a regular service migration image is required.
4. Populate the emitted service Secrets Manager containers using AWS CLI/SDK from
   an approved operator session. Values are JSON Settings fields, not `SERVICE_`
   keys. Supply `database_url` for each of nine schemas with its matching username,
   random password, emitted RDS hostname, `/telelink` and `?sslmode=require`.
   Use the established pairings in `dev/compose/setup.py` for service credentials;
   generate fresh deployed keys instead of copying local keys. The Terraform
   `app_secret_keys` catalog lists every required injected field. Optional additional
   keys can be selected with `service_secret_keys` in module wiring.
5. Supply real **test/sandbox** Stripe/Lalamove configuration; billing also needs
   `SERVICE_STRIPE_DESTINATIONS` via public environment overrides or its extra secret
   field. Fulfilment `delivery_locations_json` must be a JSON **string** containing
   the trusted destination coverage document; the startup wrapper materializes it
   privately under `/tmp`. No coverage, clinic pickup address or patient contacts
   are invented. Optional `delivery_contacts_json` can be injected similarly.
6. Store TURN `shared_secret` in its container and use the identical value as
   consultation's `turn_secret`. Signalling `signalling_secret` must match the
   consultation setting. The utility's systemd service retries configuration while
   the secret is missing; inspect it via SSM, never expose SSH. NAT and TURN share
   a small host and limited relay ports; do not claim restrictive-network/TLS TURN
   compatibility without RF01 verification.
7. Apply image/task-definition configuration with workloads **still disabled**.
   The emitted `bootstrap_task` and `migration_tasks` now exist without launching
   services. Run the bootstrap one-off task using the emitted network configuration
   and Fargate platform 1.4.0, then run and check each service's Alembic migration
   task sequentially. Bootstrap creates only owner roles/schemas, never domain data.
   Migrations use service database roles; they do not run automatically at startup.
8. Verify SES sender/recipient mailboxes in sandbox and confirm SNS alert email.
   Register the emitted Stripe webhook and put its actual signing secret into
   billing config. Cognito signup creates users, but privileged role/membership
   bootstrap and synthetic demo data must follow the existing authorized workflow.
9. Set `enable_workloads=true`. This starts the eight APIs plus signalling and the
   three Lambda functions. The schedule drains durable email jobs without requiring
   new events. Inspect health/CloudWatch before attempting the real journey.
10. Build the Vite frontend with the emitted `frontend_environment`, upload assets
    to the frontend bucket and invalidate CloudFront. Use the CloudFront origin
    consistently for login, API and video paths. Preserve API error responses.

The `demo` output contains public configuration, ARNs, endpoints and task IDs, not
secret values. Use scoped operator/CI IAM and W01's encrypted state; the Terraform
example is not a new auto-deploy workflow. ECR repository policies allow Lambda
image retrieval. Lambda/ECS still need tested IAM/network reachability and valid
service secrets. Empty secrets or dummy images do not count as a working demo.

## Routing and security details

To save one ALB, HTTPS origin paths route directly to the correct service target;
API Gateway reaches a port-80 listener restricted to workload/VPC-link security
groups. Public API paths also reach service-owned authorization on the shared
HTTPS listener. This means ALB origin access does not inherit Gateway JWT checks:
the existing backend token, role/tenant and purpose-specific service credentials
remain mandatory. This is an explicit consolidation of the original two-ALB plan,
not evidence that the original private-only ingress design is deployed.

ALB URL rewrites strip `/api/v1/<service>` for most APIs. Clinical-records and
document public routers retain their prefixes. Document's notification-context
route is a special higher-priority rewrite to `/internal/...`. Internal calls use
HTTPS origin URLs and their service credentials. Public branding image paths are
rewritten at CloudFront to the tenant API's active-clinic logo check; the private
logo bucket is never opened directly to anonymous reads. No credential/patient
payload is added to API access logs.

Redis sidecar traffic stays on task loopback. Managed Redis uses TLS and VPC
security-group isolation. RDS is private/encrypted and only workload security groups
can reach it. Secrets Manager secret versions are populated outside Terraform.
The RDS master is AWS-managed; only the one-off bootstrap task can retrieve all DB
configuration secrets. No instance SSH ingress exists. The utility uses IMDSv2.

## Verification, demonstration and teardown

Automated checks cover Singapore restriction, single-AZ DB, tiny NAT/TURN host,
no managed-cache/NAT baseline, FIFO single group, concurrency one, eight capped
API services, one signalling task, independent migrations, optional managed single
nodes and rejection of unapproved scale-out. These use mocked providers; they do
not prove AWS account quotas, ARM image compatibility, t4g availability, kernel
NAT setup, provider callbacks, sender verification or cross-network video.

Before grading, record real: Terraform plan/apply outputs; private data-store
security groups; API health; Cognito signup/login; a synthetic full patient journey;
SQS retry/DLQ and outbox recovery; authorized private PDFs; SES acceptance; CloudFront
miss/hit/error routing; queue drain with concurrency one; and normal/forced TURN
on independent networks. Keep W02-W21/I05/RF01 verification unchecked until observed.

For teardown, stop demo traffic, disable consumer/schedule work, inspect pending
financial/courier outcomes, and export any synthetic data you intend to keep. This
demo uses `skip_final_snapshot=true`: destroying RDS deletes it without a final
snapshot. Review bucket/ECR content; set `allow_destroy_demo_data=true` only when
you explicitly intend to delete that synthetic content, then review a destroy plan.
The utility disk/EIP, ALB, RDS, queues, images and other resources must all be
removed to end their recurring charges. Keep remote state until teardown is verified.
Confirm no orphan snapshots, EIPs, log groups or alternate root resources remain.
