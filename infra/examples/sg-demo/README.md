# Singapore demo example

This runnable composition illustrates `demo-platform` outside W01-owned files.
Use the agreed W01 remote-state environment for team deployment; do not deploy
the same module from two roots. Operator values belong in ignored tfvars files.

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and replace account/domain/email inputs.
2. `terraform init` and `terraform plan` for review; no automatic apply is included.
3. Follow the foundation, image, secret, migration and enablement phases in the
   [demo runbook](../../../docs/RF27-singapore-demo.md).

Default limits remain one even though CPU autoscaling policies are present.
`cost-assumptions.json` contains the dated regional pricing snapshot, not a bill.
