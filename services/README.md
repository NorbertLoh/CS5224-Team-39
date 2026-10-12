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

Business services use the FastAPI template from F03-F05 once available. Keep app code, tests and migrations inside the corresponding service. Each service supplies its own Dockerfile, health checks and deployment inputs. HTTP and worker commands may share an image while remaining independently scalable.

These directories are placeholders; no service is runnable yet.
