# TeleLink Health

CS5224 Team 39's multi-tenant teleconsultation prototype. Planned stack: React + TypeScript + Vite, independent FastAPI business services, PeerJS signalling, Floci for local AWS APIs, and AWS hosting.

## Current status

This repository contains a [React frontend](apps/web/README.md), independent business
APIs and workers, and a [full local Compose stack](docs/compose-stack.md). See the
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
| `tests/load/` | Reserved for deferred load evaluation |
| `docs/` | Setup guides, architecture decisions and runbooks |

Each business service owns its database schema and Alembic migrations. Do not write another service's tables. Frontend and backend work can be claimed separately using agreed contracts.

## Getting started

For the complete local application, follow [full-stack Compose setup](docs/compose-stack.md):
`./dev/compose.ps1 setup -Payments`, then open `https://localhost:8443`.
Existing host-stack users can preserve their database with `setup -UseExistingDatabase -Payments`.

1. Read [AGENTS.md](AGENTS.md) for the issue-first claim workflow.
2. Find a ready task in [implementation-plan.md](implementation-plan.md); create/reuse its GitHub issue and claim it before coding.
3. Read [plan.md](plan.md) for architecture, scope and the four-week schedule.
4. Run the [service template](services/template/README.md) for the F03 foundation. Follow [local setup](docs/local-development.md) as later tasks supply the full local stack. For cloud work, see [AWS setup](docs/aws-deployment.md).

Commit dependency lockfiles, migrations and sanitized configuration examples. Keep credentials, local environment overrides, generated output, Terraform state and runtime data out of Git. Use synthetic records only.

F01 is skipped by team decision. The exact demo date, AWS budget/access and infrastructure tool still need to be confirmed when relevant tasks begin.

## Local sign-in accounts

All four roles use the same **Sign in** button at http://localhost:5173 or
http://127.0.0.1:5173. Each local account uses the password `LocalDemo123!`.

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
