# AWS infrastructure and Terraform

The active team deployment is `envs/demo` in Singapore (`ap-southeast-1`). It uses
the platform's **managed** profile in domain-free mode. Demo/production describes
use and capacity; `deployment_profile` selects the implementation layout. Managed
does not mean production-ready. Read the [demo architecture](../docs/demo-architecture.md)
and [intended production architecture](../docs/production-architecture.md).

## Choose the correct root

| Path | Purpose and status | State / distinction |
| --- | --- | --- |
| `bootstrap/` | One-time state bucket and monthly Budget; historically applied under W01 | Local bootstrap state; retain its private backup |
| [envs/demo](envs/demo/README.md) | Team deployment: managed, domain-free, AMD64, singleton capacities | Shared S3 key `demo/terraform.tfstate` |
| `envs/dev/` | Provider/backend skeleton with no application module | Separate `dev/terraform.tfstate`; not a runnable application |
| [examples/sg-demo](examples/sg-demo/README.md) | Compact ARM64 reference, colocated workers, shared NAT/TURN host | Not the active demo deployment |
| [examples/sg-managed](examples/sg-managed/README.md) | Named-domain production-oriented reference with configurable scaling/failover | Still singleton defaults; no `envs/prod` exists |
| [modules/demo-platform](modules/demo-platform/README.md) | VPC, ECS, data, ingress, TURN, secrets, migrations and composition | Called by a root |
| [modules/public-edge](modules/public-edge/README.md) | CloudFront/S3 access, clinic caching and protected route forwarding | Called by the platform |
| [modules/background-jobs](modules/background-jobs/README.md) | Three Lambdas, queue mappings, dispatch schedule and alarms | Uses platform queues/network/secrets |

Use one root/state per deployment. Do not apply examples alongside the demo to the
same prefix/resources. Changing profile/state ownership requires a reviewed migration.

## Prerequisites and state

Use Terraform matching repository CI (pins 1.16.6; roots require at least 1.11 for
S3 native locking), AWS CLI v2 and an authenticated operator profile. Roots use
`allowed_account_ids` to guard the account. Floci overrides belong only in local
configuration. Real tfvars, backend files, credentials, plans, state and
`.terraform/` remain ignored; commit provider lockfiles.

Bootstrap is one-time account setup. If resources already exist, use retained
state or reviewed imports rather than fresh creation. For a new account, from
`infra/bootstrap`:

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
# Set account, agreed budget and alert recipients in the ignored file.
terraform init
terraform plan -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform output state_bucket
```

This creates the private, versioned, encrypted, TLS-only state bucket
`cs5224-team39-tfstate-<account-id>` and monthly actual/forecast budget alerts.
Bootstrap state stays local; the bucket has `prevent_destroy`. Budget alerts do
not cap spending. See [cost notes](../docs/aws-cost-notes.md).

Environment backends use an adjacent S3 lockfile. It serializes Terraform, not DB
migrations or image releases. Only force-unlock after confirming the original
operator/process has stopped.

## Deployment sequence

1. Select the root/backend and retain existing operator inputs. Review foundation
   with `enable_workloads=false`, `images={}` for a fresh deployment. Foundation
   networking/data resources still cost money while workloads are disabled.
2. Build/publish the [AMD64 release](../docs/RF31-production-release.md) for managed
   roots; pass registry digests, not local image IDs. Compact `sg-demo` needs
   matching ARM64 ECS images and cannot use that AMD64 bundle unchanged.
3. Populate Secrets Manager with owning-service JSON, including actual provider
   settings, TLS database URLs and matching pairwise service secrets. Terraform
   creates secret containers, not credential values.
4. Set the complete image map, keep workloads disabled, run emitted DB bootstrap
   then all nine migration tasks. Check logs and exit codes before proceeding.
   [Database operations](../docs/database/README.md) explain roles and execution.
5. Verify Cognito callbacks, provider webhook URLs and SES identities/recipient
   restrictions, then enable workloads. Inspect readiness and worker/Lambda health.
   Publish the frontend using fresh public Terraform outputs; the demo seed runs
   on enablement and preserves existing records.
6. Record actual journey acceptance, remaining gates and rollback evidence.
   Infrastructure validation alone does not establish a working patient journey.

See [active demo commands](envs/demo/README.md). The
[managed example](examples/sg-managed/README.md) covers named DNS, scaling and
teardown. Stop/drain work and review unresolved payment/provider outcomes before
teardown. Managed RDS/ALB protection must be disabled and applied deliberately;
retain/export versioned data and choose a unique final snapshot identifier. State,
snapshots and retained storage can remain billable after workloads stop.

## Technical mechanisms

| Mechanism | Explanation |
| --- | --- |
| Redis hold | PostgreSQL locks/index/deadline own capacity; Redis holds a TTL mirror. [Walkthrough](../services/scheduling/docs/holds.md) |
| Schema isolation | One schema/role per service, tenant IDs within schemas, no cross-owner table writes/FKs. [Database guide](../docs/database/README.md) |
| Events | Atomic domain/outbox commit, EventBridge/SQS, durable inbox deduplication and controlled DLQ replay. [Runbook](../docs/messaging-replay.md) |
| PDFs/email | Bounded Lambdas, scheduled dispatch and uncertain-send holds. [Workers](modules/background-jobs/README.md), [email](../docs/patient-emails.md) |
| Internal service route | Domain-free CloudFront path with NAT viewer-IP allowlist plus service credentials. [Demo flow](../docs/demo-architecture.md) |
| Video | Consultation admission/room assignment, PeerServer signalling, direct media with TURN fallback. [Matchmaker](../docs/RF29-signalling-matchmaker.md) |

## Changes and checks

Coordinate shared roots/modules with their issue owners. Keep reusable resources
in modules and root inputs in the owning environment. Provider `default_tags`
owns common tags. Refresh lock hashes for supported Linux/macOS/Windows platforms
when changing providers.

The infrastructure workflow validates without deployment:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra/envs/demo init -backend=false
terraform -chdir=infra/envs/demo validate
```

Mocked tests exercise wiring/capacity controls. Account-specific review, live
integration, failure and restore evidence remain rollout gates. This documentation
refresh runs no apply or live AWS inspection.
