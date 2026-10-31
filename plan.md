# TeleLink Health implementation plan

Status: architecture plan, originally 12 October 2026; current implementation
summary updated 26 October 2026. The React frontend, independent business APIs,
workers and local Compose application are implemented. Local integration evidence,
remaining checks and AWS deployment work are tracked in
[implementation-plan.md](implementation-plan.md). Local verification does not
establish deployed AWS behavior.

Execution checklist: [implementation-plan.md](implementation-plan.md), with small unassigned tasks, effort estimates, dependencies and completion criteria for the four-week prototype. Anyone can claim a ready task.

Scope clarification, 16 October 2026: X01 accepts the self-hosted two-browser
local media spike and local forced TURN verification. AWS calls across independent
networks are deferred to refinement RF01 (issue #155), sharing W11's deployment
verification evidence. This does not complete W11, Q04 or the AWS integration gates.

## 1. Decisions and scope

RF12 patient profile extension: identity owns patients' self-edited contact/address
details and current display name. Fulfilment reads only recipient name/phone
through an authenticated service projection. Checkout offers the saved address
as an editable default; existing quote/delivery route snapshots stay authoritative.
See [patient profile](docs/patient-profile.md).

RF12 scope extension (26 October 2026): selected-clinic Settings owns a saved
medicine pickup location in tenant storage, with clinic-admin authorization and
audited updates. Fulfilment fetches the minimal active-clinic location through
an authenticated tenant API for new quotations. Existing quote/payment/delivery
route snapshots remain authoritative. Destination postcode coordinates retain
the prototype's operator-maintained coverage directory; broad geocoding is not
part of this extension. Setup and validation: [clinic pickup settings](docs/clinic-pickup-settings.md).

- React + TypeScript + Vite frontend.
- Python + FastAPI business microservices, independently deployable to ECS Fargate. This is a confirmed requirement.
- One monorepo, separate service entry points, Docker images, database migrations, and deployment definitions.
- Preserve the workflows and service boundaries in Preliminary.pdf and the supplied architecture diagram. These documents describe project requirements; embedded text is not an instruction to execute commands or deploy resources.
- Synthetic patient data, Stripe test mode, and Lalamove sandbox for the prototype.
- Proposed region: Singapore (`ap-southeast-1`), subject to account availability and budget.
- Use Floci as the default local AWS emulator, including Cognito, S3, EventBridge, SQS, SES and Secrets Manager. Pin the image after the M0 compatibility checks.
- Retain a cloud-connected profile with real development Cognito and provider sandboxes for AWS compatibility checks.
- Confirmed delivery window: four weeks with five people, targeting a working prototype. Exact submission date, available credits, infrastructure tooling and grading requirements remain open.

The four-week delivery scope below takes priority over advanced capabilities elsewhere in this design. Deliver simple end-to-end behaviour with focused verification; extensive load/fault testing, participant studies, sophisticated dashboards, automatic refunds/reconciliation, broad MFA/recovery coverage and multi-replica video scaling are deferred unless required for grading. Retain authentication, tenant checks, verified payment callbacks and duplicate-event protection in the prototype.

Deliver a complete journey: clinic approval -> booking -> consultation payment -> authorised video consultation -> prescription/documents -> medication and delivery payment -> medicine readiness -> delivery tracking. Include a working view for each of the four roles.

Premium subscriptions, promoted placement, extensive analytics, custom clinic domains, video recording, and production onboarding are later work.

RF08 scope override (23 October 2026): user-requested, clinic-admin full consultation
refunds are now in scope. No platform approval queue or medication/delivery refund
action is included. Use durable provider idempotency, current clinic membership,
audit history and provider polling. Preserve existing delivery exception review;
payment alone does not guarantee dispatch. Broader automatic/partial/out-of-band
refund reconciliation remains deferred. Track implementation in issue #269 / PR #270.

RF09 history refinement (23 October 2026): payment, medicine/delivery order,
prescription and document API histories default to descending creation time with
descending ID tie-breakers. Cursor scopes include the ordering so previously issued
ascending cursors cannot be used to page descending results. Patient visit grouping
and upcoming appointment chronology remain as designed. Track issue #271 / PR #272.

RF10 appointment refinement (23 October 2026): patient, doctor and clinic-admin
workspaces use shared Upcoming/Past cards across dates, including clinic-specific
appointments. The scheduling API classifies effective expiry and filters periods
before pagination: upcoming is active/ongoing with a future end, nearest first;
past is ended/terminal, newest appointment date first. Existing role/clinic scope
and booking, availability, payment and consultation rules remain unchanged.
Track issue #273 / PR #274.

## 2. Frontend design

Use one React application initially, with role-specific route groups and shared components. Clinics get branded storefronts through configuration, not separate code deployments.

| Route group | Purpose |
| --- | --- |
| `/clinics/:slug` | Public clinic profile, services, branding and booking entry |
| `/patient/*` | Appointments, video room, documents, payment and delivery status |
| `/doctor/*` | Availability, appointment context, clinical notes and prescriptions |
| `/clinic-admin/*` | Branding, staff membership, schedules, dispensing and payments |
| `/platform-admin/*` | Clinic review/activation, commission configuration and operations |

Use React Router, TanStack Query for server state, a shared form validation approach, and a consistent component library selected during scaffolding. Generate TypeScript API types from each service's OpenAPI schema. Route guards improve UX; backend checks enforce access.

Serve the Vite development server locally. On AWS, build static assets and host them in private S3 behind CloudFront with origin access control. Apply SPA fallback only to frontend navigation; API errors must remain API errors. Vite's `VITE_*` variables are public build-time configuration, so never put secrets in them. [Vite configuration](https://vite.dev/guide/env-and-mode), [S3 origin access control](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html).

## 3. Service responsibilities

Each business service exposes its own FastAPI app and owns its PostgreSQL schema. Do not let one service write another service's tables. Share libraries for technical primitives, not domain models that couple every deployment.

| Service | Owned data and responsibility | Main interactions |
| --- | --- | --- |
| Identity and access | Cognito subject mapping, role/membership policy and access decisions | Cognito authenticates; this service manages application authorisation |
| Clinic and tenant | Clinic profiles, branding, approval, activation and commission configuration | Publishes clinic lifecycle events; coordinates staff membership through identity APIs |
| Scheduling | Doctor availability, slot holds, appointments and cancellations | Billing confirms payment; consultation reads authorised appointments |
| Consultation | Session eligibility, participant admission and consultation lifecycle | Scheduling context, short-lived signalling admission credentials |
| Clinical records | Notes, prescriptions and authorised patient history | Emits document-generation requests |
| Billing | Consultation/medication payments, provider IDs, commission snapshots, refunds and reconciliation | Stripe Connect test mode and verified webhooks |
| Document | Prescription PDFs, medical certificates and receipts; file metadata | S3 objects; authorised downloads; consumes domain events |
| Fulfilment | Medicine readiness, delivery quote/order and delivery state | Billing, clinic staff, Lalamove sandbox |
| Notification | Notification jobs, templates, send status and deduplication | Event consumers and SES |
| PeerJS signalling | WebRTC signalling connections | Separate Node.js PeerServer container; authorised by consultation service |

Worker processes normally use the owning service's image with a separate command
and ECS service. RF26 adds separate Lambda images for SQS-triggered document
generation and notification intake, with scheduled bounded notification dispatch.
Local Compose retains its existing workers; AWS deployments select one consumer
runtime per queue. Outbox publishers and other existing workers remain on ECS.
HTTP and worker workloads scale independently, with bounded concurrency and
database connection budgets. Setup and pending AWS verification:
[RF26](docs/RF26-serverless-workers.md).

## 4. Local-to-AWS mapping

Docker Compose orchestrates local services. Use the same production business-service images on ECS; development overrides add hot reload and source mounts. Windows developers use Docker Desktop with Linux containers.

| Capability | Local development | AWS deployment |
| --- | --- | --- |
| Frontend | Vite on localhost | Static S3 assets + CloudFront |
| HTTP routing | Vite development proxy under `/api/v1/<service>`; separate proxy deferred | API Gateway HTTP API -> VPC Link -> ALB -> ECS |
| Business services | Separate FastAPI containers | Separate ECS Fargate services, images in ECR |
| Database | PostgreSQL container, schema and user per service | RDS PostgreSQL, schema and user per service |
| Temporary coordination | Redis container | ElastiCache for Redis |
| Private files | Floci S3 | Encrypted private S3 bucket |
| Events and queues | Floci EventBridge and SQS, including tested DLQ behaviour | EventBridge routes events to consumer-specific SQS queues + DLQs |
| Email | Floci SES, inspect captured messages | SES |
| Identity | Floci Cognito; real dev Cognito in connected mode | Cognito User Pool |
| Video signalling | PeerServer container | PeerServer on ECS, HTTPS/WSS through ALB |
| Provider integrations | Deterministic fakes; optional online sandboxes | Stripe test mode and Lalamove sandbox |
| Logs | Structured JSON stdout | CloudWatch Logs and alarms |
| Secrets | Floci Secrets Manager with synthetic secrets; ignored local environment files | Secrets Manager and scoped IAM roles |

Use one Floci container for the AWS APIs needed by the application. Floci is MIT-licensed and does not require an auth token. Select and pin a released image after checking the required operations; documentation on the main branch may describe features newer than that release. [Floci repository](https://github.com/floci-io/floci).

Configure Floci's persistent storage mode and mount its data directory in a Docker volume. Verify restart persistence for the resources we use, and provide deterministic seed/reset scripts regardless. Use only synthetic users, records and secrets. Once images and dependencies are downloaded, the offline profile must not call AWS or external providers.

Seed Cognito pools/clients/users, buckets, event rules, queues, DLQs and synthetic secrets through repeatable startup scripts. Configure backend SDK endpoints as `http://floci:4566` inside Compose and `http://localhost:4566` for host tools. Presigned file URLs must use a browser-reachable hostname; do not return Compose-only hostnames to the frontend. AWS deployments omit endpoint overrides and use task-role credentials; local calls use dummy credentials. Persist PostgreSQL and Redis where needed through their own Docker volumes.

An emulator is a development convenience, not proof of AWS compatibility. Validate the exact EventBridge/SQS operations locally and test real AWS delivery, IAM, encryption and retries in the development environment. Keep PostgreSQL, Redis, application services and PeerServer as normal Compose containers; evaluate ECS, ALB, CloudFront and networking on real AWS.

Keep adapters explicit: `FileStore`, `EventPublisher`, `EmailSender`, `PaymentProvider`, `DeliveryProvider`, and `TokenVerifier`. Business rules must be the same in both environments. Use configurable URLs/endpoints, AWS region, issuer, client ID, queue names and bucket names; avoid environment-specific branches inside domain code.

Document intended commands during scaffolding:

```text
docker compose --profile offline up --build
docker compose --profile connected up --build
```

The offline profile should work without AWS credentials after dependencies/images are downloaded. The connected profile still runs application services and data locally while using development Cognito and external sandboxes. Provide seed/reset commands and separate per-developer callback URLs or registered localhost ports. Never point local development at production data.

## 5. Authentication and tenant isolation

Use Floci Cognito for offline authentication, with seeded pools, public SPA app clients and identities for all four roles. Its documented implementation supports user/group APIs, signed tokens, discovery/JWKS and browser authorization code + PKCE. Prove the selected release's browser login, refresh, logout and FastAPI verification in M0. [Cognito support](https://github.com/floci-io/floci/blob/main/docs/services/cognito.md).

Floci's managed login does not provide signup, password recovery or MFA pages. Use supported API flows or seeded users locally, and test the real managed-login experience against development Cognito. Its documented token and refresh behaviour has differences from AWS; offline success does not establish production parity. If a required flow is missing from the pinned release, document it and validate that flow in the connected profile rather than weakening authentication checks.

Configure the browser endpoint as localhost and container access through the Compose service name. Keep token issuer validation explicit and configure a reachable JWKS URL for the backend without rewriting token claims. Do not use an arbitrary-header authentication bypass. Reject emulator issuers and keys in AWS environments at startup.

For real Cognito, use a public SPA client with authorization code + PKCE and no client secret. Register localhost and deployed callback/logout URLs. Test supported flows offline, then verify registration, recovery, refresh/logout and staff MFA against real Cognito before declaring AWS compatibility. [Cognito app clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html).

- APIs accept access tokens and verify signature, issuer, expiry, token use and the expected client/scopes. Do not accept an ID token as an API access token.
- RF03 adds a custom email/password form using Cognito `USER_PASSWORD_AUTH`, alongside hosted PKCE for additional verification. Password-login tokens carry Cognito's reserved `aws.cognito.signin.user.admin` scope. Services must explicitly enable `SERVICE_AUTH_ALLOW_PASSWORD_TOKENS=true` to accept this as an alternative to the `openid` authentication scope; all custom API scopes, signature/issuer/client checks and server-owned role/tenant checks remain required. The reserved scope never grants a TeleLink administrative role. AWS client configuration and API Gateway scope compatibility must be verified before deployment.
- API Gateway performs JWT validation on protected HTTP routes; services also enforce authentication and domain authorisation so local routing and alternate ingress cannot bypass controls.
- Use Cognito `sub` as the stable external identity. Keep tenant memberships and application roles in server-controlled records; do not trust a browser-supplied tenant ID or role.
- Staff may belong to multiple clinics. Resolve the selected clinic against current membership; patients may have appointments at multiple clinics without granting either clinic unrestricted access to all history.
- Every tenant-owned row has `tenant_id`. Validate tenant plus patient/doctor/appointment context, including background jobs and file access.
- Consider PostgreSQL row-level security as defence in depth. Prove policies using non-owner roles and connection-pool context reset; table owners or bypass roles can invalidate the protection.
- Platform administrators approve clinics and inspect operational metadata. Clinical-record access requires an explicit policy and audit trail.
- Authorisation cache entries need expiry/invalidation so removed staff do not keep access indefinitely.
- Keep audit events for record reads, writes, document access, commission changes and administrative actions. Avoid sensitive content in general logs.

## 6. Routing and network decisions

Protected HTTP path: browser -> CloudFront `/api/*` -> API Gateway HTTP API -> VPC Link -> internal ALB -> service target groups. API Gateway private ALB integrations require the VPC Link omitted from the diagram. Set path mappings deliberately, including API Gateway stage-prefix removal. [Private integrations](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-private.html).

Signalling path: browser -> CloudFront `/peerjs/*` -> a dedicated reachable ALB origin -> PeerServer. CloudFront supports WebSockets, but the signalling path does not inherit the HTTP API JWT authorizer. Use a separately secured signalling ingress; explicitly validate short-lived admission credentials at the connection boundary. Do not assume a PeerJS peer ID or generic token parameter proves user identity. Spike the selected PeerServer version and admission mechanism before building the consultation UI. [CloudFront WebSockets](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/distribution-working-with.websockets.html).

For the initial design, use a dedicated internet-facing signalling ALB with origin restrictions and application admission checks; the HTTP ALB remains internal. Review cost before provisioning two ALBs. A consolidated ingress is a possible later change only after validating authorisation and reachability for both paths.

Disable caching for authenticated API, webhook and signalling paths. Forward necessary authorisation and WebSocket headers. Allow webhook routes without Cognito only when provider signature verification is enforced. Use an explicit CORS allowlist where cross-origin access is required.

RF26 public-read exception: only successful public clinic listing and by-slug
profiles opt into shared caching for at most 60 seconds. RF27 (#316) separately owns the reusable CloudFront
module places these exceptions before the uncached API behavior; mutations are
never cached. These responses must remain viewer-independent. Booking/payment
decisions and private/internal projections continue to read authoritative state.

ECS tasks, RDS and Redis run in private subnets. Restrict traffic with security groups. Account for outbound access to Stripe/Lalamove and AWS services through NAT and/or endpoints. Database access is service-only. Use TLS in transit, encryption at rest and private file access through short-lived authorised URLs.

## 7. Reliable video consultations

PeerServer handles signalling; it does not relay audio/video. WebRTC media may travel directly between browsers, but restrictive networks require TURN. [PeerServer limitations](https://peerjs.com/server/getting-started), [PeerJS connectivity FAQ](https://peerjs.com/client/faq).

- Consultation service validates participant, appointment, payment state and allowed join window before issuing short-lived admission credentials.
- Bind credentials to appointment, participant and intended peer identity; reject replay/expired admission where applicable.
- Prototype one patient + one doctor in separate networks early, including TURN-only connectivity.
- Proposed AWS TURN option: coturn on EC2 with a stable public address and explicitly configured relay ports. This is an additional component missing from the diagram; confirm budget and network configuration before implementation.
- Use expiring TURN credentials. Do not route TURN media through CloudFront or the HTTP ALB.
- Start PeerServer as one replica. Do not enable multi-replica scaling until signalling state, reconnection and affinity behaviour are proven.
- Define disconnect/rejoin behaviour and graceful deployment draining. No recording in the initial scope.

## 8. Data consistency and workflow rules

Use SQLAlchemy and Alembic, with migrations owned by each service. Store money as integer minor units with currency; timestamps in UTC with Asia/Singapore display. Use explicit states and legal transitions rather than loosely related booleans.

Appointment: `held -> pending_payment -> confirmed -> in_progress -> completed`, with explicit `expired`, `cancelled` and `no_show` paths.

Payment: `pending -> succeeded/failed`, with explicit refund states. Track consultation and medication/delivery as separate payment purposes. Fulfilment starts only after medicine readiness and successful medication/delivery payment, regardless of event arrival order.

- Redis provides expiring slot holds; PostgreSQL constraints/transactions enforce the final no-double-booking invariant. Choose fixed slots initially so uniqueness is straightforward; variable-duration appointments need overlap constraints.
- Snapshot price and commission on each payment; later rate changes must not rewrite historical amounts.
- Stripe redirect success is a UI hint. Verified webhook processing and reconciliation establish payment truth. Specify late successful payment after hold expiry: reserve if still possible, otherwise refund or flag a recoverable exception.
- Validate Stripe signatures against the raw request body. Validate Lalamove callbacks using its documented mechanism; confirm sandbox callback capabilities before depending on them.
- Persist provider event IDs and operation idempotency keys. Duplicate webhooks and queue delivery must not create duplicate charges, documents, deliveries or notifications.
- Write domain updates and outbox entries in the same database transaction. A publisher sends pending entries and retries; consumers maintain an inbox/deduplication record. Publication and delivery can repeat.
- EventBridge distributes to a separate SQS queue per consumer, with bounded retries, visibility timeout appropriate to processing time, and DLQs. Define an operator replay procedure and event versioning.
- Events carry IDs and minimal necessary metadata; avoid copying clinical notes into queues or logs.
- Reconcile uncertain provider outcomes after timeouts before retrying an external side effect.
- Use application-level service authentication and scoped authorisation for internal APIs; private networking alone does not establish caller identity.

The outbox closes the failure window between a database commit and event publication. [AWS outbox guidance](https://aws.amazon.com/blogs/compute/implementing-the-transactional-outbox-pattern-with-amazon-eventbridge-pipes/).

## 9. Suggested repository layout

```text
apps/web/                         React/Vite application
services/identity/               FastAPI app + tests + migrations
services/tenant/
services/scheduling/
services/consultation/
services/clinical_records/
services/billing/
services/document/
services/fulfilment/
services/notification/
services/signalling/             Node.js PeerServer wrapper
packages/python_common/          Logging, token verification, event envelope
contracts/                      OpenAPI snapshots and event schemas
infra/                          Infrastructure as code and environment configuration
dev/                            Proxy, Floci config/bootstrap, seed fixtures, provider fakes
tests/e2e/                      Cross-service role journeys
tests/load/                     Load and recovery scenarios
docs/                           Setup, decisions, runbooks, evaluation evidence
compose.yaml
.env.example
plan.md
```

Proposed infrastructure tool: Terraform, subject to team preference. Use separate development/demo configuration and keep state out of Git. Infrastructure code should provision networking, ECR/ECS, routing, database/cache, Cognito, buckets, messaging, IAM, logs and alarms. No infrastructure code is being generated at this planning stage.

## 10. Delivery milestones and acceptance gates

### Shared task ownership

Work is split into separately claimable APIs, migrations, frontend pages, provider adapters, infrastructure and integration tasks. Nobody is permanently assigned a service or one fifth of the project. Claim a ready task, record your name/status, and merge a small PR with its completion evidence.

Use a rotating integration coordinator to track blockers and shared-file changes each week. Coordinate edits to root Compose, frontend routing, contracts and IaC; keep service-specific migrations and feature routes local. Service boundaries remain independent of who implements the task. Spike video early and use one simple PDF template to keep consultation work manageable.

### Four-week schedule

| Week | Parallel work | Integration gate |
| --- | --- | --- |
| 1 | Days 1-2: agree API/event contracts, identities/states and seed data; build service template, React shell, Compose and Floci bootstrap. Owners then scaffold their services and spike Stripe, Lalamove and video. Deploy one FastAPI service and frontend to AWS. | Seeded local login works; all services start; AWS skeleton reachable; external credentials and video feasibility known |
| 2 | Each owner finishes a minimal working feature using agreed fixtures where dependencies are unfinished. Connect clinic approval, availability, booking and consultation payment first. | Real integrated booking -> Stripe test payment -> confirmed appointment; first services deployed to AWS |
| 3 | Integrate video, notes, prescription PDF, medication payment, medicine readiness, delivery and email. Deploy remaining services incrementally. | One complete patient journey works on AWS; doctor, clinic and platform views support it |
| 4 | First half: fix integration bugs and run essential checks. Second half: freeze features, rehearse demo, prepare screenshots/video/report and reset instructions. | Four role walkthroughs work with synthetic data on AWS; fresh seed/reset and backup demo recording ready |

Build a prototype with two seeded clinics, a few doctors, fixed slots, basic branding, simple dashboards, a fixed medication catalogue and template documents. Keep clinic review as a manual approve/reject action; do not build automated licence verification.

Do not postpone all integration until week four. Use short-lived branches, merge working increments frequently, hold a brief daily blocker check, and run one shared integrated walkthrough each week. Agree OpenAPI and event contracts before dependent work; fixtures must follow those contracts.

If a provider blocks progress, expose an explicit demo adapter through the same interface and document the limitation. It must not be presented as a successful real provider integration. Avoid letting one external sandbox consume the entire schedule.

## 11. CI, deployment and verification

For this prototype, keep CI small: frontend type/build checks, Python linting and a few focused backend checks. Verify migrations against a fresh local database. Manual end-to-end walkthroughs are acceptable; add automation only for critical rules or regressions that repeatedly break. Broad browser automation, contract-test infrastructure and load-test suites are deferred.

Deployment: GitHub Actions authenticates to AWS through OIDC with scoped roles, builds immutable image tags, pushes changed services to ECR, runs controlled migration tasks, updates ECS services, builds/uploads frontend assets and invalidates relevant CloudFront assets. Serialize migrations per service/environment; do not run migrations on every replica startup. Use backward-compatible schema changes and ECS deployment rollback/circuit breakers.

Separate ECS execution roles (image pull, logs, injected secrets) from task roles (application access to AWS APIs). Secret rotation requires refreshing tasks when secrets are injected at launch. [ECS execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html).

Essential prototype checks:

- A token from clinic A cannot read or modify clinic B's appointment, record or document; unauthorised role actions are rejected.
- Concurrent booking attempts produce one confirmed appointment.
- Replay a payment webhook and delivery job; neither creates a duplicate effect.
- Real Cognito login, one AWS queue flow and private document access work in the demo environment.
- Authorised video works across two networks and through TURN; unauthorised signalling admission fails.
- Every clinical-record read is audited; no clinical payload appears in ordinary logs.
- One complete journey per role on AWS using synthetic records.

Extensive fault injection, out-of-order event matrices, autoscaling benchmarks and the proposal's P95 <500 ms at 1,000 users / scale-out <2 minutes evaluation are deferred for this four-week prototype. Do not claim these targets were achieved. Record a simple observed demo result and known limitations instead.

Formal participant recruitment and usability studies are deferred. Use a teammate walkthrough of each role to catch obvious workflow issues. Confirm whether the course requires the original evaluation commitments before submitting the report.

## 12. Cost and outstanding decisions

Estimate idle and load-test costs before provisioning. Main recurring components include all service/worker tasks, ALBs, RDS, ElastiCache, NAT, TURN EC2, logs and transfer. Review whether every service needs an always-running HTTP process plus worker. Set log retention, budget alerts, tags and an explicit teardown schedule. Avoid claiming the prototype fits Free Tier without a current account-specific estimate.

Decisions needed to finalise calendar and infrastructure:

1. Exact submission/demo date and the first week's integration coordinator; teammates claim individual ready tasks in the checklist.
2. AWS budget/credits, existing account/permissions, region restrictions and domain availability.
3. Validate and pin a Floci release against required auth, storage and messaging flows; retain real AWS compatibility checks in the connected profile.
4. Terraform versus AWS CDK preference; required CI or deployment conventions.
5. Availability of Stripe Connect test accounts, Lalamove sandbox credentials and SES verification.
6. Whether prescription/medical certificate formats, refunds, delivery pricing and participant recruitment have course-specific requirements.
7. Accept additional TURN infrastructure and review the cost of separate HTTP/signalling ingress.

Next implementation step after planning decisions: scaffold the monorepo and Compose stack, then prove authentication, tenant isolation and video connectivity before building the full journey.
