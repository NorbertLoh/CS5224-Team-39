# Managed AWS services with one replica (RF27)

This is the production-oriented **service layout**, deliberately sized for a small
synthetic demonstration. It uses the reusable platform module's `managed` profile.
It is executable Terraform, not a deployed/verified production environment.

The cheaper [sg-demo](../sg-demo/README.md) composition remains available. Local
Docker Compose is unchanged. Select one deployment root/state; do not apply both
profiles to the same resource prefix or use this as an in-place profile migration.

## Services selected

| Responsibility | AWS service/configuration | Explicit capacity limit |
| --- | --- | --- |
| Web frontend | Private versioned S3, CloudFront with origin access control | AWS-managed delivery; no ECS frontend task |
| Authentication | Cognito user pool and public SPA client | Existing signup/password/PKCE integration; service quotas apply |
| Public APIs | API Gateway HTTP API, JWT authorizer, VPC Link | Existing throttles; successful public clinic reads remain cached up to 60 seconds |
| API ingress | Separate internal ALB, HTTPS listener and verified server name | One ALB service, mandatory two-AZ subnets; no public API listener rules |
| Eight business APIs | ECS Fargate in a private subnet, ARM64, digest-pinned ECR images | Desired/min/max one task per API; 0.25 vCPU and existing 0.5–1 GiB sizes |
| Existing worker loops | Five independent ECS worker groups: scheduling, billing, clinical records, document, fulfilment | One task per group, each 0.25 vCPU and 0.5–1 GiB; loops within a group share its task |
| PDFs/notifications | Document Lambda, notification intake Lambda, scheduled dispatch Lambda | One concurrent invocation per function; FIFO consumer group/batch one |
| Database | Private encrypted RDS PostgreSQL 17, db.t4g.micro, 20-GiB gp3 | One instance, no standby/read replicas or storage auto-growth |
| Cache | Private encrypted TLS ElastiCache Redis cache.t4g.micro | One node, no replica/failover |
| Internet egress | Managed public NAT Gateway and its Elastic IP | One gateway in one AZ |
| Video signalling | Separate public HTTPS ALB → private ECS PeerServer | One signalling task; admission checks remain mandatory |
| Media relay | Dedicated t4g.nano coturn EC2 with its own Elastic IP, SSM and encrypted disk | One host; it does not forward private-subnet traffic |
| Files and logos | Separate private versioned S3 buckets, authorised document downloads | Nonempty buckets are not force-deleted |
| Events and email | EventBridge, SQS and consumer DLQs, SES | Existing event/idempotency semantics and provider quotas |
| Configuration | Secrets Manager, owning-service IAM roles | Operator-populated secrets; no secret values passed to Terraform |
| Operations | CloudWatch logs/alarms, SNS email and AWS Budget | Fourteen-day API/worker/Lambda/API Gateway logs; budget is an alert |
| State | Existing encrypted S3 backend with native state locking | Use the team's W01-owned bootstrap and restricted operator role |

When fully enabled there are **14 Fargate tasks**: eight APIs, five worker groups
and one signalling task. There are also three Lambda functions, one RDS instance,
one ElastiCache node and one TURN EC2 instance. "One replica" is per workload,
not one container for the whole application. ALB/CloudFront/S3 and other managed
services operate their own infrastructure; their internal replication is not
controlled by the ECS limit.

Every API autoscaling target has min/max one. Worker/signalling desired count is
one. ECS deployments use minimum healthy 0%, maximum 100%, so the old task stops
before its replacement starts. This enforces the requested deployment ceiling at
the cost of downtime. Guardrails reject scale-out, a sidecar cache, instance-based
NAT and destructive bucket cleanup in this profile.

## Request paths and TLS

Browser API calls use CloudFront → API Gateway → VPC Link → private HTTPS ALB →
private API task. Gateway verifies JWTs on protected routes; APIs still verify
token use, role/tenant access and internal service credentials. Public directory
and signed Stripe callback exceptions retain their existing checks.

Internal service calls use `https://<internal_origin_hostname>/api/v1/<service>`.
The public signalling ALB exposes PeerJS paths only; API and internal document
routes are absent there. Security groups admit port 8000 to API tasks only from
the private ALB, and port 9000 from the signalling ALB. The two paths have separate
VPC Link/ALB security groups.

Supply two **different owned names within the supplied public Route53 zone**:
`origin_hostname` for signalling and `internal_origin_hostname` for internal API
TLS. The internal name resolves to the internal ALB's private addresses; publishing
DNS does not make the ALB internet-reachable. No private Route53 zone is created.
Use a Singapore certificate covering both names, or leave the certificate ARN
null to request/DNS-validate both names automatically. API Gateway sets the TLS
server name; internal clients validate the same public certificate normally.

TLS ends at the private ALB; ALB-to-API task traffic remains HTTP within its
restricted security groups. This is not end-to-end application TLS. Browser
WebSockets use the separate HTTPS signalling origin. TURN is a separate direct
TCP/UDP service on 3478 with bounded UDP relay ports; TURN-over-TLS is not added.

## Configure and review

Requires Terraform 1.11+, AWS provider 6.71–6.x, an existing W01-owned encrypted
state bucket, AWS operator credentials and an owned public DNS zone. W01 PR #233
owns `infra/bootstrap`, `infra/envs/*` and their state structure; this root does
not create or replace those files.

From this directory:

```powershell
Copy-Item backend.hcl.example backend.hcl
Copy-Item terraform.tfvars.example terraform.tfvars
# Replace state bucket/key and account, hostnames, zone, sender and alert email.
terraform init -backend-config=backend.hcl
terraform fmt -check
terraform validate
terraform plan -out=managed.tfplan
```

Do not place AWS credentials or service secret values in either file. Configure
SSO/profile/assumed-role access outside Terraform. The bucket must already have
encryption, public-access blocking and restricted IAM; `encrypt=true` requests
encrypted state and `use_lockfile=true` enables S3 native locking. Backend example
values are placeholders. Generated plans/state and operator files are ignored.

Keep `enable_workloads=false` and `images={}` while reviewing/provisioning the
foundation. As in the [deployment sequence](../../../docs/RF27-singapore-demo.md),
then publish ARM64 ECS and AMD64 Lambda images, populate service Secrets Manager
JSON, register test-provider callbacks, bootstrap DB roles/schemas, run each owning
service's migration task, verify SES and enable workloads. No Redis image is needed.
Upload the frontend using the emitted environment/CloudFront URL.

`SERVICE_ENVIRONMENT=production` selects normal application production guards and
disables default API docs. It does not turn sandbox-only adapters into live
providers: continue using synthetic data, Stripe test mode and Lalamove sandbox.
Use fresh deployed secrets with the existing service pairings. Confirm private
DNS/TLS and RDS/cache reachability from API, worker and Lambda workloads.

This layout costs more than sg-demo: five additional Fargate worker tasks, a second
ALB, managed NAT with per-GB processing, another public IP, longer logs and versioned
storage are provisioned even with one replica. The old sg-demo total is not this
profile's estimate. Obtain an account-specific plan and current pricing estimate
before enabling it; the example's $250 budget only sends alerts and is not a cap.

## Data protection and intentional teardown

RDS has seven-day backups, deletion protection and a required final snapshot on
deletion. Both ALBs have deletion protection. S3 versioning is enabled; nonempty
buckets cannot be force-destroyed by this profile. These controls do not prove
backup restore or disaster recovery.

For reviewed teardown, stop traffic/consumer work, inspect pending payment/courier
outcomes and preserve required data. Set a unique `final_snapshot_identifier` and
set `deletion_protection=false` in the same managed profile. Review/apply that
protection-only change before reviewing a destroy plan. Do not switch to the demo
profile to unlock deletion: that would also change routes and worker placement.
Nonempty/versioned buckets require explicit export and object/version deletion
through the normal operator process. Final DB snapshots and the remote-state
bucket remain billable after workload teardown; retain/delete them deliberately.

## Verification and limits

Validation and tests use the real provider schema with mocked AWS resources.
They check managed routing/TLS, dedicated non-NAT TURN, separate worker containers,
one-replica bounds, data/log protections, certificate SANs and teardown controls.
CI validates both example roots and all three modules. No AWS apply, account-specific
plan, provider transaction or local Compose/application change is performed here.

Local verification on 4 November 2026: Terraform 1.11.4 / AWS provider 6.71.0;
module and managed example validate successfully; all 13 mocked Terraform runs
passed, including the original demo/sidecar checks and managed layout guards.

This is a production-oriented **single-replica staging/demo footprint**. It does
not provide HA, zero-downtime deployments, RDS/cache failover, TURN host replacement,
TURN TLS, fine-grained per-process IAM, staff MFA, WAF, full audit/access logging,
tested restore, a live-provider rollout or validated production capacity. Small
task/database sizes and connection budgets need real measurement. Service choices
are in place; those production acceptance gates remain separate work.
