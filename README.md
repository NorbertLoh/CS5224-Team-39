# TeleLink Health

CS5224 Team 39's multi-tenant teleconsultation prototype. Planned stack: React + TypeScript + Vite, independent FastAPI business services, PeerJS signalling, Floci for local AWS APIs, and AWS hosting.

## Current status

This repository contains plans, a directory scaffold and a runnable [FastAPI service template](services/template/README.md). The frontend, business features, Dockerfiles, Compose configuration and AWS infrastructure are not implemented yet. The template runs independently without AWS or a database.

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

F01 is skipped by team decision. The exact demo date, AWS budget/access and infrastructure tool still need to be confirmed when relevant tasks begin.
