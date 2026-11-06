# Compact Singapore demo reference (ARM64)

This is a cost-saving alternative, **not the active team demo**. The selected
[demo root](../../envs/demo/README.md) uses managed ingress, separate worker groups,
NAT Gateway, TURN ASG and AMD64 images; see its [architecture](../../../docs/demo-architecture.md).
This compact profile colocates workers with APIs and shares a NAT/TURN host: nine
Fargate tasks rather than fourteen. Its costs do not describe the managed demo.
The managed AMD64 release bundle does not match this example's ARM64 ECS tasks.

This runnable composition illustrates `demo-platform` outside W01-owned files.
Use the agreed W01 remote-state environment for team deployment; do not deploy
the same module from two roots. Operator values belong in ignored tfvars files.

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and replace account/domain/email inputs.
2. `terraform init` and `terraform plan` for review; no automatic apply is included.
3. Follow the foundation, image, secret, migration and enablement phases in the
   [demo runbook](../../../docs/RF27-singapore-demo.md).

Default limits remain one even though CPU autoscaling policies are present.
The example selects one shared private TLS ElastiCache Redis `cache.t4g.micro`
with encryption at rest and no replicas/failover. It does not run a Redis sidecar.
`cost-assumptions.json` contains the dated regional pricing snapshot, not a bill.
