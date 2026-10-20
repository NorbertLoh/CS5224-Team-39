# AWS development and demo deployment

Status: Terraform skeleton only (W01). No resources have been provisioned.

Infrastructure is Terraform in [infra/](../infra/README.md): a one-time `bootstrap` root for remote state and the budget, plus `envs/dev` and `envs/demo`. It targets one shared team AWS account in `ap-southeast-1`. Cost estimates and the teardown schedule are in [aws-cost-notes.md](aws-cost-notes.md). W02-W21 add the resources and deployment workflow. Before provisioning, confirm account permissions, the budget amount and demo availability requirements.

Record infrastructure commands, environment configuration, GitHub-to-AWS authentication, per-service image builds, controlled migrations, frontend publishing, health checks, logs, provider callbacks and teardown steps as they are implemented.

Keep local Floci endpoint overrides out of AWS configuration. Use scoped execution/task roles and Secrets Manager for service credentials. Record an observed cost estimate and shutdown plan; do not assume Free Tier coverage.
