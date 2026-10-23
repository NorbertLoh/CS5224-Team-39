# AWS infrastructure

Terraform configuration for the shared team AWS account in `ap-southeast-1`. W01 chose Terraform and created the layout below; later W-tasks add the actual resources. Nothing has been provisioned yet.

| Path | Purpose |
| --- | --- |
| `bootstrap/` | One-time account setup: remote state bucket and monthly cost budget. Uses local state. |
| `envs/dev/` | Development environment root. State key `dev/terraform.tfstate`. |
| `envs/demo/` | Demo environment root. State key `demo/terraform.tfstate`. Can be created and destroyed on its own. |
| `modules/` | Shared modules called from both environments (added from W02 onwards). |

Cost estimates, budget alerts and the teardown schedule are in [docs/aws-cost-notes.md](../docs/aws-cost-notes.md).

## Prerequisites

- Terraform 1.16.x (`>= 1.11` is required for S3 native state locking). CI pins 1.16.6.
- AWS CLI v2 with credentials for the shared team account, for example `aws configure sso` or an access-key profile. Set `AWS_PROFILE` before running Terraform.
- Each root sets `allowed_account_ids`, so Terraform refuses to run against any other account.

## One-time bootstrap (one teammate, once per account)

```sh
cd infra/bootstrap
cp terraform.tfvars.example terraform.tfvars   # set account ID, budget and alert emails
terraform init
terraform apply
terraform output state_bucket
```

This creates a versioned, encrypted, TLS-only, private S3 bucket named `cs5224-team39-tfstate-<account-id>`, plus a monthly AWS Budget that alerts at 50%, 80% and 100% of actual spend and at 100% of forecast spend. Bootstrap state stays local and is gitignored. If that state is lost, re-import the bucket and budget instead of creating new ones. The bucket uses `prevent_destroy`, so remove that setting only for the final teardown.

## Working with an environment

```sh
cd infra/envs/dev                               # or envs/demo
cp backend.hcl.example backend.hcl              # set bucket = <state_bucket output>
cp terraform.tfvars.example terraform.tfvars    # set aws_account_id
terraform init -backend-config=backend.hcl
terraform plan -out=dev.tfplan
terraform apply dev.tfplan
```

State locking uses an S3 lockfile next to the state object, so two teammates cannot apply the same environment at once. If a crashed run leaves a stale lock, confirm nobody else is applying, then run `terraform force-unlock <lock-id>`.

## Conventions

- **Names:** prefix resources with the `name_prefix` local (`cs5224-team39-dev` or `cs5224-team39-demo`).
- **Tags:** the provider's `default_tags` apply `Project`, `Environment` and `ManagedBy`. Do not repeat them per resource.
- **Both environments:** put shared resource definitions in `modules/` and call them from both `envs/dev` and `envs/demo`, so the environments do not drift. Keep sizes and counts as environment variables.
- **Coordinate first:** IaC changes are shared files. Coordinate with whoever is working on another W-task before editing the same root or module.
- **Lock files:** commit `.terraform.lock.hcl`. After changing provider versions, refresh hashes for every platform:
  `terraform providers lock -platform=linux_amd64 -platform=linux_arm64 -platform=darwin_amd64 -platform=darwin_arm64 -platform=windows_amd64`
- **Never commit:** state, plan files, `.terraform/`, `terraform.tfvars`, `backend.hcl` or credentials. All are covered by the root `.gitignore`. Keep secrets in Secrets Manager, not in tfvars.
- **Local endpoints:** keep Floci endpoint overrides out of this configuration.

## Checks

CI (`.github/workflows/infra-checks.yml`) runs these checks without credentials or a backend:

```sh
terraform fmt -check -recursive
terraform -chdir=<root> init -backend=false
terraform -chdir=<root> validate
```
