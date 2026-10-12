# TeleLink Health

CS5224 Team 39's multi-tenant teleconsultation prototype. Planned stack: React + TypeScript + Vite, independent FastAPI business services, PeerJS signalling, Floci for local AWS APIs, and AWS hosting.

## Current status

This repository contains plans and a directory scaffold. Application code, dependency manifests, Dockerfiles, Compose configuration and AWS infrastructure are not implemented yet. There is currently no runnable application or startup command.

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
4. Follow [local setup](docs/local-development.md) once the foundation tasks supply executable configuration. For cloud work, see [AWS setup](docs/aws-deployment.md).

Commit dependency lockfiles, migrations and sanitized configuration examples. Keep credentials, local environment overrides, generated output, Terraform state and runtime data out of Git. Use synthetic records only.

F01 is skipped by team decision. The exact demo date, AWS budget/access and infrastructure tool still need to be confirmed when relevant tasks begin.
