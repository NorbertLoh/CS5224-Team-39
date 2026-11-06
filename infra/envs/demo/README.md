# Team AWS demo root

This is the selected team root with shared `demo/terraform.tfstate`. It calls
`demo-platform` with `deployment_profile="managed"`, `domain_free=true`, AMD64
containers, NAT Gateway, managed Redis and non-destructive demo-account seeding.
See the [demo architecture](../../../docs/demo-architecture.md).

Unlike the compact ARM64 `examples/sg-demo`, it separates APIs and worker groups.
Unlike the named `examples/sg-managed`, it needs no Route53 zone, owned domain or
ACM certificate. This root does not expose replica/failover inputs; module defaults
keep them at one. There is no prod root; see the [production target](../../../docs/production-architecture.md).

## Configure and review

From this directory, with Terraform/AWS CLI and the intended operator profile:

```powershell
Copy-Item backend.hcl.example backend.hcl
Copy-Item terraform.tfvars.example terraform.tfvars
# Set existing state bucket, account, actual SES sender and budget recipient.
$env:AWS_PROFILE = 'YOUR_DEMO_PROFILE'
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out=demo.tfplan
```

For existing deployments retain the operator files and image map; replacing them
with empty examples can disable workloads. Review the actual plan before
`terraform apply demo.tfplan`. Foundation-only mode (`images={}` and workloads
disabled) still incurs networking/data costs. Keep operator files/plans ignored.

## Release sequence

Follow the [infrastructure sequence](../../README.md#deployment-sequence):
foundation, published AMD64 images, populated Secrets Manager, DB bootstrap, all
nine owner migrations, provider checks, enablement and frontend publication.
The emitted `platform` output supplies cluster/task/network IDs and public settings.
See [database task execution](../../../docs/database/README.md#aws-bootstrap-and-migration-tasks).
API startup does not migrate.

Use the [release tooling](../../../docs/RF31-production-release.md). Its generated
image var-file deliberately sets workloads disabled for migrations; explicitly
review the later enablement plan. Rebuild frontend settings from fresh outputs,
including authenticated PDF downloads. Upload hashed assets first, `index.html`
last; preserve old assets for cached clients and rollback.

The account seed needs Node.js/AWS CLI on the operator machine and permission to
run ECS tasks/pass roles. It runs on first enablement, re-enablement or seed task
definition change. The `platform.demo_login_secret` output locates the private
login roster; do not commit/print credentials. See [seed and receipt secret pairings](../../../docs/RF32-domain-free-demo.md#demo-accounts).

## Operations and limits

Browser traffic uses the generated CloudFront HTTPS/WSS hostname. CloudFront VPC
origins and VPC Link reach private ALBs over HTTP inside the VPC. The
`/service/<owner>` path checks actual viewer NAT IP and still requires service
credentials. The default CloudFront certificate uses AWS's default protocol
policy; it does not configure an owned-domain TLS policy.

At full enablement: 14 Fargate tasks, three Lambdas, one RDS primary, one Redis
node, one NAT Gateway and one TURN instance. Managed data protections apply;
singletons and automatic replacement do not establish HA. Inspect readiness,
queue/DLQ age, outbox backlog and uncertain email/provider outcomes. Use the
[replay runbook](../../../docs/messaging-replay.md) for recovery.

Use the [managed teardown procedure](../../examples/sg-managed/README.md#data-protection-and-intentional-teardown).
Do not switch profiles to bypass protection or force-delete retained data. Actual
AWS acceptance gaps remain in the backlog; this refresh makes no live health claim.
