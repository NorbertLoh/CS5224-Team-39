# Managed AWS scaling/failover with demo capacity limits (RF27)

This is the production-oriented **service layout**, with scaling/replacement and
HA settings built in and demo capacities defaulted to one. It uses the reusable
platform module's `managed` profile.
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
| Eight business APIs | ECS Fargate in private subnets, AMD64, digest-pinned ECR images, CPU target tracking and unhealthy-task replacement | Demo min/max one; configurable through min_tasks/max_tasks |
| Existing worker loops | Five independent ECS worker groups with CPU target tracking | Demo min/max one; eligible groups can scale; fulfilment polling remains singleton |
| PDFs/notifications | Document Lambda, notification intake Lambda, scheduled dispatch Lambda | Demo concurrency one; configurable reservations, FIFO group/batch ordering remains |
| Database | Private encrypted RDS PostgreSQL 17, db.t4g.micro, 20-GiB gp3 | Demo primary only; database_multi_az enables standby/failover |
| Cache | Private encrypted TLS ElastiCache Redis cache.t4g.micro | Demo one node; redis_node_count >= 2 enables replicas, Multi-AZ and automatic promotion |
| Internet egress | Managed public NAT Gateway and its Elastic IP | Demo one; nat_gateway_count=2 creates a gateway and local route in each AZ |
| Video signalling | Public HTTPS ALB, private ECS PeerServer and PostgreSQL room assignments | Demo min/max one; scales with min_tasks/max_tasks |
| Media relay | Coturn Launch Template/Auto Scaling Group, readiness hook, protocol health agent, CPU scaling and stable EIP pool | Demo min/desired/max one; configurable fleet and hot redundancy across AZs |
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

Demo API/worker autoscaling min/max and TURN ASG min/desired/max are one. Mechanisms
are provisioned even though the ceilings currently prevent scale-out. ECS and ASG
replace unhealthy instances/tasks automatically. At one, replacements have downtime.
At API/worker minimum two, deployments retain at least 50% healthy and maximum 100%,
so replacement does not require an extra replica beyond the configured count.

## Raising capacity later

`capacity.tf` and `terraform.tfvars.example` hold demo values; the architecture
does not prohibit increasing them. `allow_scale_out=true` explicitly permits
larger values. The **non-default** `scale-two.tfvars.example` overlay raises API
and signalling min/max, eligible worker min/max, TURN fleet and Lambda reservations to two, enables
the RDS standby, adds a Redis replica and enables two AZ-local NAT gateways:

```powershell
terraform plan -var-file=scale-two.tfvars.example -out=scale-two.tfplan
```

This only plans when run by an operator with real account inputs. It is not
automatically loaded/applied. Increasing minimum to two provisions hot capacity;
raising only maximum to two allows reactive scale-out but retains one at low load.
Only real AWS/load/failure tests can establish availability and capacity. RDS/cache
standby/replica semantics differ from ECS task counts. Small instance sizes and DB
connection budgets must be reviewed before increasing concurrent work.

ECS desired counts are initially set from the minima, then managed by Application
Auto Scaling (Terraform ignores subsequent desired-count drift). TURN desired is
also an initial seed owned by its ASG thereafter; min/max changes enforce bounds.
Raise minimum to two for sustained hot capacity. Disabling workloads sets TURN
min/max to zero, intentionally stopping the fleet; stop/drain traffic first.

Fulfilment's grouped tracking loop stays at one poller per provider account.
Lambda FIFO consumers retain one producer message group. Parallelism within
those workloads requires separate ordering and coordination changes.

RF29 uses PostgreSQL to assign both participants to one live PeerServer. The
managed profile enables private node forwarding and ECS task protection. Apply
consultation migration `0005` and publish matching consultation, signalling and
frontend builds before enabling or scaling the workload. See
[RF29 deployment and recovery](../../../docs/RF29-signalling-matchmaker.md).

## TURN replacement and future relay redundancy

The managed profile uses a Launch Template and Auto Scaling Group across both
public AZ subnets. Defaults are `turn_capacity={min=1,desired=1,max=1}`. With
workloads disabled the fleet is zero so missing setup secrets do not cause a
bootstrap replacement loop. Enabling workloads starts the configured capacity.

Each host claims a free EIP from a Terraform-owned pool sized to the configured
maximum. Association explicitly forbids stealing another host's address; existing
ownership is reused without repeated remapping. An old host's address becomes
available when that instance is terminated. Pool addresses survive replacements.
All pool URLs are advertised in the consultation ICE configuration, so raising
the maximum reserves additional addresses before they necessarily have a relay.
Unassigned pool EIPs are still billable and may temporarily fail ICE attempts.

Bootstrap reads the TURN shared secret, writes a private coturn config, starts
coturn and completes the launch lifecycle hook only after a local STUN binding
response. Failed bootstrap is abandoned/replaced after the 15-minute hook deadline.
Systemd restarts coturn; a one-minute timer marks the owning InService host unhealthy
after three failed protocol checks, respecting ASG's five-minute health grace.
EC2 status checks also drive replacement. The agent uses IMDSv2, pool-scoped address
association and a fleet-scoped lifecycle/health policy. Read-only discovery calls
use wildcard resources as required by AWS. Monitor ASG activity and instance
journals; deployment still needs real IAM/bootstrap verification.

CPU target tracking is configured at 60%, bounded by the configured maximum.
Automatic scale-in is disabled to avoid terminating active relay allocations;
drain calls and reduce capacity deliberately. Instance refresh uses the launch
template's numeric version and honours 0/100 at minimum one or 50/100 at minimum
two. Rotating the shared secret requires a reviewed refresh/restart as well.

At two, there are two independently addressed relays available for ICE selection;
there is no stateless load balancer pretending to migrate TURN allocations. Active
calls on a failed relay may require an ICE restart/rejoin. Terraform provisions the
fleet, not client reconnection behavior. Local STUN health does not prove public
reachability, authenticated relay allocation or real media quality; test forced
TURN across independent networks and kill one relay before claiming failover.

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
then publish AMD64 ECS and Lambda images, populate service Secrets Manager
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
They check managed routing/TLS, TURN ASG/lifecycle/address bounds, separate worker
containers, demo-one/future-two capacities, RDS/cache failover settings, AZ-local
NAT routes, data/log protections, certificate SANs and teardown controls.
CI validates both example roots and all three modules. No AWS apply, account-specific
plan, provider transaction or local Compose/application change is performed here.

Local verification on 4 November 2026: Terraform 1.11.4 / AWS provider 6.71.0;
module and managed example validate successfully; all 13 mocked Terraform runs
passed, including demo-one and future-two scaling layouts. Ten standalone Python
unit checks cover TURN address ownership/races, protocol response validation,
configuration safety, launch readiness and health-driven replacement reporting.

This is a production-oriented architecture with **demo capacities of one**.
Automatic replacement is configured; hot HA needs the larger settings, and real
failover has not been exercised. TURN TLS, client ICE recovery, multi-replica
PeerJS room routing, fulfilment poller coordination, fine-grained per-process IAM,
staff MFA, WAF, full audit/access logging, tested restore, live-provider rollout
and production capacity remain separate acceptance work. Increasing a number
does not prove these application/network behaviors. Local Compose is unchanged.
