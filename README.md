# TeleLink Health

CS5224 Team 39's multi-tenant teleconsultation prototype: React/TypeScript, independent FastAPI services, PostgreSQL, Redis and PeerJS/WebRTC. Docker Compose uses Floci for local AWS APIs; the AWS demo uses managed AWS services in Singapore.

## Current status

This repository contains a [React frontend](apps/web/README.md), independent business
APIs and workers, a [full local Compose stack](docs/compose-stack.md), and a
[Terraform-managed AWS demo](docs/demo-architecture.md). See the
[implementation backlog](implementation-plan.md) for completed local integrations
and remaining journey/AWS work. The [FastAPI template](services/template/README.md)
can also run independently.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/web/` | React/Vite frontend with role-specific feature routes |
| `services/` | Independent business-service apps, tests and migrations; Node.js signalling service |
| `packages/python_common/` | Shared technical utilities, not shared domain models |
| `contracts/` | API/event contracts and development fixtures |
| `infra/` | AWS infrastructure code and environment configuration |
| `dev/` | Compose support, Floci configuration/bootstrap and synthetic seed tools |
| `tests/e2e/` | Focused cross-service workflow checks |
| `docs/` | Setup guides, architecture decisions and runbooks |

Each business service owns its database schema and Alembic migrations. Do not write another service's tables. Frontend and backend work can be claimed separately using agreed contracts.

## Documentation

| Need | Current guide |
| --- | --- |
| Understand the system from overview to implementation | [Technical architecture guide](docs/architecture-guide.md) |
| Run the complete local app | [Compose setup](docs/compose-stack.md) |
| Understand the AWS demo and its limits | [Demo architecture](docs/demo-architecture.md), [demo Terraform](infra/envs/demo/README.md) |
| Understand the intended production deployment | [Production architecture](docs/production-architecture.md), [managed Terraform example](infra/examples/sg-managed/README.md) |
| Configure, release or tear down AWS resources | [Infrastructure README](infra/README.md) |
| Understand database ownership, tables and migrations | [Database and schemas](docs/database/README.md) |
| Understand Redis holds and double-booking protection | [Booking hold internals](services/scheduling/docs/holds.md) |
| Sign-in and session behavior | [Authentication](docs/authentication.md) |
| Frontend setup and checks | [Web README](apps/web/README.md) |
| Booking and Upcoming/Past appointments | [Scheduling frontend](docs/scheduling-frontend.md) |
| Clinical notes, prescriptions and PDFs | [Records setup](docs/records-frontend.md), [documents](docs/document-frontend.md) |
| Payment callbacks and refunds | [Billing webhooks](services/billing/WEBHOOKS.md), [refunds](services/billing/REFUNDS.md) |
| Local tools and synthetic data | [Development support](dev/README.md) |
| Architecture, contracts and remaining work | [Architecture](plan.md), [contracts](contracts/README.md), [backlog](implementation-plan.md) |

Task-specific evidence is historical unless explicitly dated as a new verification.
Use current setup guides and package scripts when reproducing checks.

## Getting started

For the complete local application, follow [full-stack Compose setup](docs/compose-stack.md):
`./dev/compose.ps1 setup -Payments`, then open `https://localhost:8443`.
Existing host-stack users can preserve their database with `setup -UseExistingDatabase -Payments`.

1. Read [AGENTS.md](AGENTS.md) for the issue-first claim workflow.
2. Find a ready task in [implementation-plan.md](implementation-plan.md); create/reuse its GitHub issue and claim it before coding.
3. Read [plan.md](plan.md) for architecture, scope and the four-week schedule.
4. Run the [full local Compose stack](docs/compose-stack.md), or the [service template](services/template/README.md) for isolated foundation work. For cloud work, see [AWS setup](infra/README.md).

Commit dependency lockfiles, migrations and sanitized configuration examples. Keep credentials, local environment overrides, generated output, Terraform state and runtime data out of Git. Use synthetic records only.

F01 is skipped by team decision. W01 chose Terraform with a shared team AWS account in `ap-southeast-1`. RF32 and later releases record AWS demo deployment; this does not establish production readiness or completion of the remaining journey/video acceptance gates. The configured AWS Budget sends alerts; it does not cap spending.

## Local sign-in accounts

All four roles use the same **Sign in** button at https://localhost:8443 with
the full Compose stack. Host-only frontend URLs depend on the callback registered
by that setup guide. Each local account uses the password `LocalDemo123!`.

| Role | Email |
| --- | --- |
| Patient | `patient@example.test` |
| Doctor | `doctor@example.test` |
| Clinic administrator | `clinic@example.test` |
| Platform administrator | `platform@example.test` |

Follow [clinic backend setup](docs/clinic-backend.md) to create the local Cognito
accounts, provision their backend roles and link the doctor to the local clinic.
These accounts are for local Floci development only. Backend roles and clinic
memberships determine access; Cognito groups alone do not grant permissions.
Use [full-stack Compose](docs/compose-stack.md) to run the implemented role pages
against the local services.

## AI Declaration
ChatGPT 6.1 Sol was used for the following
- Writing and managing GitHub Issues
- Used for development but implementation plan and idea is by us
- AI suggested the use of workers which we accepted
