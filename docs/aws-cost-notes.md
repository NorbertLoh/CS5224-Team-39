# AWS cost notes

Status: planning estimate (W01). Nothing has been provisioned. Do not assume the prototype fits within the Free Tier.

All figures are approximate on-demand prices for `ap-southeast-1` (Singapore). Confirm them in the [AWS Pricing Calculator](https://calculator.aws/) before W02 provisions anything. Replace these estimates with observed Cost Explorer figures once resources exist.

## Account and budget

- One shared team AWS account. `dev` and `demo` are separate Terraform environments, told apart by the `Environment` tag.
- **Open item:** the budget/credit amount has not been confirmed (F01 was skipped). Record it here and set `monthly_budget_usd` in `infra/bootstrap` when it is known.
- `infra/bootstrap` creates a monthly AWS Budget. It alerts at 50%, 80% and 100% of actual spend and at 100% of forecast spend. The first two budgets per account are free.
- After bootstrap, activate the `Project` and `Environment` cost allocation tags in the Billing console, so Cost Explorer can split spend by environment. Tags take up to 24 hours to appear.

## Main recurring costs

These assume the architecture in `plan.md`, with one small instance of each workload running 24/7:

| Component | Assumption | Approx. hourly | Approx. monthly |
| --- | --- | --- | --- |
| ECS Fargate tasks | ~14 tasks (10 HTTP services + ~4 workers), 0.25 vCPU / 0.5 GB each | ~$0.22 | ~$160 |
| NAT gateway | 1 gateway, plus ~$0.06/GB processed | ~$0.06 | ~$45 |
| Application Load Balancers | Internal HTTP ALB + internet-facing signalling ALB, plus LCU charges | ~$0.05 | ~$37 |
| RDS PostgreSQL | `db.t4g.micro`, single-AZ, 20 GB gp3 | ~$0.03 | ~$23 |
| ElastiCache Redis | `cache.t4g.micro`, single node | ~$0.025 | ~$18 |
| TURN server (EC2) | `t4g.small` coturn with an Elastic IP | ~$0.03 | ~$19 |
| Public IPv4 addresses | Signalling ALB (2 AZs), NAT gateway, TURN (~$0.005/hour each) | ~$0.02 | ~$15 |
| Secrets Manager | ~10 secrets at $0.40/month | — | ~$4 |
| CloudWatch Logs, ECR, S3, CloudFront, HTTP API, SQS, EventBridge, SES, Cognito | Demo-level traffic with synthetic users | — | small (< ~$10) |

**Total if everything runs continuously: roughly $300+/month, or about $10/day.** Fargate tasks and the NAT gateway make up most of it, so they are the main levers.

## Cost controls

- **Tear down when idle.** Create `demo` only for rehearsals and the final demo, then `terraform destroy` it. In `dev`, destroy or scale down at the end of each work session rather than leaving it running overnight.
- **Scale tasks to zero.** Set ECS desired counts to 0 when `dev` is idle. Consider whether each low-traffic service really needs a separate always-running worker (`plan.md` §12).
- **NAT gateway.** This is the largest fixed cost. Use one gateway, not one per AZ. VPC interface endpoints cost ~$0.013/hour per AZ each, so several of them cost more than one NAT gateway. W02 should compare the options before provisioning.
- **RDS.** A stopped instance only incurs storage costs, but AWS restarts it automatically after 7 days.
- **Log retention.** Set every CloudWatch log group's retention explicitly, for example 7 days in `dev` and 14 days in `demo` (W21). Never leave it at "never expire".
- **Tags.** Every resource gets `Project`, `Environment` and `ManagedBy` through provider `default_tags`.
- **Reviews.** Review the cost of the second ALB and the TURN EC2 instance before W11 provisions them (`plan.md` §12, decision 7).

## Teardown schedule

1. **During development:** destroy or scale down `dev` after each session. `demo` exists only around rehearsals.
2. **After the final demo:** `terraform destroy` in `envs/demo`, then in `envs/dev`.
3. **After grading:** remove `prevent_destroy` from the state bucket in `infra/bootstrap`, empty the bucket (including all object versions), then `terraform destroy` the bootstrap root. Check Cost Explorer a few days later for leftover charges, such as snapshots, Elastic IPs, ECR images or log groups.
