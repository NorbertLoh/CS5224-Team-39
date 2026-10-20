# TeleLink Health

CS5224 Team 39's multi-tenant teleconsultation prototype. Planned stack: React + TypeScript + Vite, independent FastAPI business services, PeerJS signalling, Floci for local AWS APIs, and AWS hosting.

## Current status

This repository contains a [React frontend](apps/web/README.md), a runnable [FastAPI service template](services/template/README.md), and [local Compose dependencies](docs/local-development.md). Business-service integration and AWS infrastructure remain planned work. The template can run independently without AWS or a database.

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

1. Read [AGENTS.md](AGENTS.md) for the issue-first claim workflow.
2. Find a ready task in [implementation-plan.md](implementation-plan.md); create/reuse its GitHub issue and claim it before coding.
3. Read [plan.md](plan.md) for architecture, scope and the four-week schedule.
4. Run the [service template](services/template/README.md) for the F03 foundation. Follow [local setup](docs/local-development.md) as later tasks supply the full local stack. For cloud work, see [AWS setup](docs/aws-deployment.md).

Commit dependency lockfiles, migrations and sanitized configuration examples. Keep credentials, local environment overrides, generated output, Terraform state and runtime data out of Git. Use synthetic records only.

F01 is skipped by team decision. W01 chose Terraform with a shared team AWS account in `ap-southeast-1` (see [infra/README.md](infra/README.md)). The exact demo date and AWS budget amount still need to be confirmed.

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
Currently, the clinic list, storefront and profile editor are implemented; the
remaining role pages are still planned.
