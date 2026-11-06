# Independently deployable services

| Directory | Responsibility |
| --- | --- |
| `identity/` | Subject mapping, memberships, roles and access policies |
| `tenant/` | Clinic profiles, branding, activation and commission configuration |
| `scheduling/` | Availability, holds and appointments |
| `consultation/` | Session eligibility, admission and lifecycle |
| `clinical_records/` | Notes, prescriptions and authorised history |
| `billing/` | Payment state, Stripe integration and commission snapshots |
| `document/` | PDF generation, metadata and private downloads |
| `fulfilment/` | Medication readiness, delivery quotes/orders and tracking |
| `notification/` | Event-driven email jobs and send status |
| `signalling/` | Node.js PeerServer and admission validation |

Use [template/](template/README.md) for the FastAPI foundation and its optional [SQLAlchemy/Alembic example](template/docs/database.md). F05 adds container builds. Keep app code, tests and migrations inside the corresponding service. Each service supplies its own Dockerfile, health checks and deployment inputs. HTTP and worker commands may share an image while remaining independently scalable.

The business services are implemented and run together through the
[Compose stack](../docs/compose-stack.md) or the [AWS demo](../infra/envs/demo/README.md).
See [database and schemas](../docs/database/README.md) for table ownership,
cross-service references, migration commands and Redis booking-hold behavior.
