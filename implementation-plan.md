# TeleLink Health: shared implementation backlog

Five people, four weeks. Anyone can claim any ready task. Architecture: [plan.md](plan.md).

## Claiming and finishing tasks

All tasks start unassigned and unchecked. Add `Assignee: <name>; status: in progress` to the task you claim. Check its dependencies first. A task is ready when all listed dependencies are merged; `none` means it can start immediately. Prefer one task per PR, with branch names such as `feat/S03-slot-holds`.

Each row is a separately claimable deliverable. Effort is a rough focused-work estimate: S = 1-3 hours, M = half a day, L = about a day. Estimates exclude waiting for credentials and integration debugging. Split an L task further if it becomes larger. Week labels indicate priority, not a restriction on when to start.

UI work can start against the agreed API fixtures after its listed contract dependency; replace mocks during integration. Do not check an integration task until real services work together. Check implementation tasks after merging, meeting their completion criterion, and recording a brief verification/setup note.

Coordinate changes to shared Compose, routing, contracts and infrastructure files before editing them. Claiming one task does not reserve the entire service. Use feature route modules and service-local migrations to reduce conflicts. Appoint a rotating integration coordinator each week to track blockers; this person does not implement everything.

Completion audit, 16 October 2026: reconciled all 127 task rows with open/closed
GitHub issues, open/merged PRs and the current implementation. **61 tasks are complete,
F01 is skipped by user decision, and 65 tasks remain unfinished.** The 62 checked
rows include that skipped task. Completed work comprises F02-F16, C01-C05,
A01-A11, U01-U08, S01-S07, R01-R04, U12-U13, P01-P03, M01-M04, D01 and B01.
D01 is recorded after merged PR #131 and closed issue #130; B01 after merged
PR #138 and closed issue #137; P02 after merged PR #144 and closed issue #128;
P03 after merged PR #148 and closed issue #147. Open PRs and merged
partial previews do not count as completed tasks. Verification below records the
evidence reported for each implementation; this documentation audit did not rerun
runtime checks or establish new integration/AWS evidence.

Current claims and remaining blockers:

| Work | Current status and remaining work |
| --- | --- |
| X01 / U11 / consultation | X01 issue #56 / open PR #57 still needs observed cross-network audio/video and forced TURN evidence. U11's preview merged in PR #127, but issue #126 stays open until real remote calling works. X02 and V02-V04 still depend on unfinished admission/video work; V01's listed dependencies are complete. |
| Billing | B01 completed in merged PR #138; issue #137 closed. Its 89 PostgreSQL tests and CI passed. X03 Stripe checkout/Connect and X04 webhook verification remain unchecked. B02-B07 and the real billing handoff are unfinished; S05/S06 fixtures do not establish billing integration. |
| Documents | P02 completed in merged PR #144; issue #128 closed. The authenticated/audited records projection, trusted current-name lookups and stored-PDF worker passed local transport/replay/recovery checks and CI. P03 completed in merged PR #148; issue #147 closed. Authorised/audited lists and signed downloads passed 89 document tests, local HTTP verification and CI. Address/registration fields remain optional prototype omissions. U14 and AWS privacy/download verification remain unfinished. |
| Records / fulfilment | D01 merged with an explicitly permitted dispensing fixture, not real order integration. C04's authenticated dispensing projection and its HTTP adapter remain missing. R04 completed in merged PR #142; issue #141 closed. Real frontend records saves, issuance and catalogue integration passed local HTTP verification. Browser/AWS and actual consultation/payment journeys remain unverified. |
| Delivery | D02 issue #134 is assigned to NorbertLoh and blocked by unchecked X05 Lalamove sandbox verification. D01 is complete; D03/D04 have complete listed dependencies. D05-D07 still depend on quote/readiness/payment/delivery work. |
| AWS / integration | W01-W21 remain unchecked. F01 was skipped, so AWS budget/access and the IaC choice still need resolution before affected provisioning. Issue #54 tracks real Cognito revocation/private-document checks. I01-I05, Q01-Q06 and E01-E04 remain unchecked; service-level tests and local emulator evidence do not complete these gates. |

Unclaimed tasks with complete listed dependencies: X03, X05, U09, U10, V01,
D03, D04, U15, U16, N01 and Q02. These are candidates to claim, not new
assignments. W01 additionally needs the AWS decisions above. P02/P03 are complete;
U14 is claimed by NorbertLoh in issue #150 / PR #151; review/merge pending.
For every other unchecked task, the Depends on column identifies unfinished
prerequisites; an unchecked task is not necessarily blocked by external access.

## Week 1: setup and contracts

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [x] | F01 | **Skipped by user decision.** Exact deadline and AWS budget/access remain open in `plan.md`; confirm them before affected deployment tasks. | none | S |
| [x] | F02 | Create repo structure, ignore rules and setup README placeholders. Completed in merged PR #2. | none | S |
| [x] | F03 | Create FastAPI template with settings, logging, health/readiness and OpenAPI. Completed in merged PR #4. | F02 | M |
| [x] | F04 | Add SQLAlchemy/Alembic example and fresh-database migration instructions. Completed in merged PR #6. | F03 | M |
| [x] | F05 | Add production Dockerfile and local reload override for the template. Completed in merged PR #10; image build, health checks and local reload verified. | F03 | S |
| [x] | F06 | Scaffold React/TypeScript/Vite; build succeeds. Completed in merged PR #11; TypeScript, production build and browser checks passed. | F02 | S |
| [x] | F07 | Add router, role layouts and feature route registration. Completed in merged PR #12; all four role layouts, feature routes and fallbacks verified. | F06 | M |
| [x] | F08 | Add query client, typed API client and loading/error components. Completed in merged PR #16; tests, lint and production build passed. | F06, C01 | M |
| [x] | F09 | Create Compose PostgreSQL/Redis/Floci services and environment examples. Completed in merged PR #20; all three services passed startup, health and smoke checks. | F02 | M |
| [x] | F10 | Add template API to Compose and Vite API forwarding; documented startup works. Completed in merged PR #23; four healthy containers, dev/preview API forwarding and Swagger verified. Separate proxy container deferred by user decision. | F05, F09 | M |
| [x] | F11 | Bootstrap Floci S3 and synthetic secrets; repeated bootstrap is safe. Completed in merged PR #25; resource settings, safe reruns and object/secret preservation verified. | F09 | S |
| [x] | F12 | Bootstrap event bus, consumer queues/rules and DLQs; deliver one message. Completed in merged PR #29; all six routes and queued-message preservation verified. | F09, C05 | M |
| [x] | F13 | Bootstrap Floci Cognito pool/public client and four-role synthetic users. Completed in merged PR #31; stable IDs/passwords/disabled-state reruns, four PKCE logins, signed access tokens and redirect/Compose configuration verified. Issue #30 closed. | F09 | M |
| [x] | F14 | Create shared fixtures for two clinics, doctors and workflow entities. Completed in merged PR #40; linked two-clinic dataset, validator, 12 integrity tests, lint and CI passed. | C01-C05 | M |
| [x] | F15 | Add minimal frontend build/type and backend lint checks in CI. Completed in merged PRs #18 and #44; clean frontend install/lint/type/build, backend Ruff and all push/PR CI checks passed. Issue #17 closed. | F03, F06 | S |
| [x] | F16 | Verify Floci restart persistence and required APIs; pin a released image. Completed in merged PR #53; issue #43 closed. Core six-service API/state/recreation/offline checks passed; Floci 2.2.0 manifest pinned for reproducibility. User accepted local revocation-reload and S3 access/expiry limitations; real AWS verification stays open in issue #54 (W05/W08/P03). Full results: `docs/floci-verification.md`. | F11-F13, A01-A03 | M |
| [x] | C01 | Document IDs, money, timestamps, errors, pagination and API prefixes. Completed in merged PR #15; examples verified. | none | S |
| [x] | C02 | Define identity/membership, clinic and appointment access APIs with fixtures. Completed in merged PR #36; resource links, access-denial examples and C01/C05 consistency verified. | C01 | M |
| [x] | C03 | Define booking/payment states, hold expiry and late-payment behaviour. Completed in merged PR #37; amount splits, expiry boundary, late-payment recovery and C05 consistency verified. | C01 | M |
| [x] | C04 | Define prescription/order/quote APIs and ownership of trusted prices. Completed in merged PR #38; prescription/order links, trusted totals, commission and paid/ready delivery gating verified. | C01 | M |
| [x] | C05 | Define event envelope, producers/consumers and sample workflow events. Completed in merged PR #27; fixtures validated and F12 consumer routing reviewed. | C01 | M |
| [ ] | X01 | Spike self-hosted PeerJS across two networks; document TURN ports/setup. Assignee: NorbertLoh; status: in progress. Issue #56 / open PR #57; cross-network call and forced TURN evidence remain required. | none | L |
| [ ] | X02 | Spike appointment-bound signalling admission; reject unrelated users. | X01 | M |
| [ ] | X03 | Verify Stripe test checkout, Connect access and commission capability. | none | M |
| [ ] | X04 | Verify Stripe webhook signatures against a sample raw-body callback. | X03 | S |
| [ ] | X05 | Verify Lalamove sandbox quote/order/status and callback verification. | none | M |

C02-C05 each need a quick review by someone building a consuming feature. They do not need a meeting with all five people. Use temporary fixtures for feasibility spikes and keep credentials out of Git. If sandbox access is blocked, record it immediately and implement an explicitly labelled adapter for demo continuity.

Setup/contracts are complete. Claim a ready task from the audit above; X03 and X05 verification unblock billing and delivery respectively. X01 is already claimed and must not be duplicated.

## Week 1-2: authentication and clinics

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [x] | A01 | Add React PKCE login/return flow against Floci; obtain access token. Completed in merged PR #49; four-role browser PKCE, callback cleanup/reload and signed API access verified. Issue #46 closed. | F07, F13 | M |
| [x] | A02 | Add refresh/logout handling and expiry UX; verify pinned emulator behaviour. Completed in merged PR #49; automatic refresh, expiry UX, revocation and hosted logout verified on Floci 2.2.0; OAuth refresh limitation documented. Issue #47 closed. | A01 | M |
| [x] | A03 | Add FastAPI token verification: JWKS, issuer, expiry, token use and client. Completed in merged PR #49; strict RS256/JWKS access-token verification, invalid-token tests, non-local config guards and container/browser integration passed. Issue #48 closed. | F03, F13 | M |
| [x] | A04 | Create identity service schema/migrations for subjects, roles and memberships. Completed in merged PR #59; 29 PostgreSQL tests, schema isolation, lint and CI passed. Issue #58 closed. | F04, C02 | M |
| [x] | A05 | Add membership/access APIs and service authentication; reject arbitrary identity headers. Completed in merged PR #61; 81 tests, live Floci identity mapping and CI passed. Issue #60 closed; subsequent tenant/membership integration completed in A08/A10 and A11. | A03, A04 | M |
| [x] | A06 | Add reusable tenant/role checks and apply them to one template endpoint. Completed in merged PR #63; shared foundations, 124 local tests, real HTTP authorization, container checks and CI passed. Issue #62 closed. | A05 | M |
| [x] | A07 | Create tenant service schema/migrations for clinic, branding and activation. Completed in merged PR #65; 30 PostgreSQL tests, migration isolation, lint and CI passed. Issue #64 closed. | F04, C02 | M |
| [x] | A08 | Add clinic create/update/public-profile APIs; inactive clinics cannot accept bookings. Completed in merged PR #67; 165 tests, real Floci/two-service HTTP checks and CI passed. Issue #66 closed. | A06, A07 | M |
| [x] | A09 | Add platform approve/reject and commission-setting APIs with audit events. Completed in merged PR #69; 94 tenant tests, live Floci/platform HTTP checks and CI passed. Issue #68 closed. | A08 | M |
| [x] | A10 | Add staff assignment/membership APIs with authorised clinic administration. Completed in merged PR #71; 205 tests, live two-service HTTP staff lifecycle/authorization checks and CI passed. Issue #70 closed. | A05, A08 | M |
| [x] | U01 | Build branded clinic storefront using fixtures. Completed in merged PR #73; 17 frontend tests, desktop/mobile browser checks, component output parity and CI passed. Issue #72 closed; live integration remains A11. | F07, F08, C02 | M |
| [x] | U02 | Build clinic profile/branding editor. Completed in merged PR #75; profile saves persist in PostgreSQL, logo upload/replacement/removal uses S3, and all implemented clinic pages use real APIs with local/AWS configuration. 22 frontend, 100 identity and 113 tenant tests, browser Save/Discard/reload/login checks and CI passed. Issue #74 closed; remaining staff/admin integration stays in A11. | F07, F08, C02 | M |
| [x] | U03 | Build staff management page using real identity/tenant APIs. Completed in merged PR #79; staff assignment, role changes, revocation/reactivation and last-admin protection verified with live local services; 22 frontend tests, lint/build and CI passed. Issue #78 closed. Browser visual and AWS checks remain unverified. | F07, F08, C02 | M |
| [x] | U04 | Build platform clinic approval and commission pages using real identity/tenant APIs. Completed in merged PR #81; compact clinic list links to individual management pages. Live review/commission persistence, validation, authorization and detail API checks passed; 22 frontend tests, lint/build and CI passed. Issue #80 closed. Browser interaction, multi-page pagination and AWS checks remain unverified. | F07, F08, C02 | M |
| [x] | U05 | Add role navigation, validated clinic selection and login/logout controls. Completed in merged PR #83; shared auth/role navigation, clinic route validation, email staff assignment and readable memberships verified with real local APIs. 111 identity and 31 frontend tests, lint/build and CI passed. Issue #82 closed. Browser interaction/visual checks and AWS integration remain unverified. | A01, A02, F07, C02 | M |
| [x] | A11 | Connect clinic/staff/admin pages to real identity and tenant APIs. Completed in merged PR #85; issue #84 closed. Real local HTTP integration, 32 frontend tests, focused cursor regression and CI passed. Browser login/profile/staff checks passed partially; remaining platform browser and AWS checks are unverified. Evidence: `docs/clinic-integration.md`. | A08-A10, U01-U05 | M |

## Week 2: scheduling and booking

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [x] | S01 | Create scheduling schema/migrations: fixed availability slots and appointments. Completed in merged PR #89; 45 PostgreSQL tests, schema isolation, lint and CI passed. Issue #88 closed. | F04, C02, C03 | M |
| [x] | S02 | Add doctor availability and patient slot-list APIs with access checks. Completed in merged PR #91; 94 tests, real Floci/three-service HTTP verification and CI passed. Issue #90 closed. | S01, A06, A08 | M |
| [x] | S03 | Add expiring Redis holds plus database reservation constraint/transaction. Completed in merged PR #93; 127 PostgreSQL/Redis tests, real Floci/HTTP hold and expiry checks and CI passed. Issue #92 closed. | S02, F09 | L |
| [x] | S04 | Add appointment list/detail/cancel APIs and legal state transitions. Completed in merged PR #95; 174 PostgreSQL/Redis tests, live HTTP checks and CI passed. Issue #94 closed. | S03 | M |
| [x] | S05 | Consume consultation-payment success idempotently and confirm appointment. Completed in merged PR #101; 201 PostgreSQL/Redis tests, live Floci EventBridge/SQS verification and CI passed. Issue #100 closed. Billing reads/checkout remain explicit fixtures pending real billing integration; late recovery subsequently completed in S06 (PR #110). | S04, M03, C05 | M |
| [x] | S06 | Handle expired hold/late payment as an explicit recoverable exception. Completed in merged PR #110; guarded recovery, audit and durable billing exception delivery verified with 217 PostgreSQL/Redis tests, live Floci transport and passing CI. Issue #109 closed. Billing adapters remain explicit fixtures pending real billing integration; provider refunds and AWS integration remain unverified. | S05 | S |
| [x] | U06 | Build doctor availability editor using fixtures. Completed in merged PR #103; weekly timetable supports multiple selections, click/drag deselection and protected batch edits. All 43 frontend tests, lint, build, Prettier checks, local browser checks and CI passed. Issue #102 closed; live scheduling integration remains S07. | F07, F08, C02 | M |
| [x] | U07 | Build patient slot picker and booking/checkout handoff using fixtures. Completed in merged PR #108; clinic Book entry, date dropdown, 30-minute slot cells and checkout preview. 48 frontend tests, lint/build and CI passed. Issue #107 closed; live integration remains S07/B07, browser visual checks unverified. | F07, F08, C03 | M |
| [x] | U08 | Build patient/doctor/clinic appointment list and detail views using fixtures. Completed in merged PR #106; role-scoped date dropdown, half-hour cells and appointment details with focused components. Combined 53 frontend tests, lint/build and CI passed. Issue #105 closed; live integration remains S07, browser visual checks unverified. | F07, F08, C02, C03 | M |
| [x] | S07 | Connect availability/booking/appointment pages to real scheduling APIs. Completed in merged PR #112; 60 frontend tests, lint/build, real frontend adapter walkthrough with cleanup and CI passed. Issue #111 closed. Browser interaction and AWS remain unverified; billing checkout remains B07. | S04, U06-U08 | M |

## Week 2: payments

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [x] | B01 | Create billing schema/migrations for charges, provider IDs and commission snapshots. Completed in merged PR #138; 89 PostgreSQL tests, migration isolation/round-trips, SQL/ORM snapshot protection, lint/format and CI passed. Issue #137 closed. | F04, C03, C04 | M |
| [ ] | B02 | Add consultation checkout API with trusted price and appointment linkage. | B01, X03, A06 | M |
| [ ] | B03 | Add raw-body webhook signature verification and event-ID deduplication. | B02, X04 | M |
| [ ] | B04 | Save payment changes and outbox event in one transaction; publish success. | B03, M02, C05 | M |
| [ ] | B05 | Add authorised payment status/list APIs and basic commission totals. | B03, A06 | M |
| [ ] | B06 | Add medication/delivery checkout with validated order/quote totals. | B04, C04 | M |
| [ ] | U09 | Build checkout return/pending/failure/success screens using fixtures. | F07, F08, C03 | M |
| [ ] | U10 | Build clinic payments and simple commission summary using fixtures. | F07, F08, C03 | M |
| [ ] | B07 | Connect payment pages and scheduling handoff to real billing APIs. | B02, B05, U09, U10, S07 | M |

## Week 2-3: consultation, records and files

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [ ] | V01 | Create consultation service schema and session start/end/join-window rules. | F04, C02 | M |
| [ ] | V02 | Add admission API validating actual appointment, participants and payment. | V01, A06, S04, X02 | M |
| [ ] | V03 | Package PeerServer with admission validation and local HTTPS/WSS routing. | X02, F10 | M |
| [ ] | U11 | Build video room, camera/mic controls and disconnect/rejoin states. PR #127 supplies role-protected patient/doctor layouts, local media controls and expanded join/leave previews; remote PeerJS/TURN calling remains blocked by X01 #56. Issue #126 stays In progress. | F07, X01 | L |
| [ ] | V04 | Connect video room to admission and booked appointment pages. | U11, V02, V03, S07 | M |
| [x] | R01 | Create clinical-record schema/migrations for notes and prescriptions. Completed in merged PR #125; 34 PostgreSQL tests, migration isolation, lint and CI passed. Issue #123 closed. | F04, C04 | M |
| [x] | R02 | Add appointment-scoped doctor write and patient read APIs; audit reads. Completed in merged PR #132; 81 PostgreSQL/API/adapter tests, live Floci/identity/scheduling HTTP checks and CI passed. Issue #114 closed. D01's catalogue integration was subsequently verified in R04 (merged PR #142); browser/AWS checks remain unverified. The service-only document projection subsequently completed in P02 (merged PR #144); the dispensing projection remains missing. | R01, A06, S04 | M |
| [x] | R03 | Publish prescription-issued event through outbox. Completed in merged PR #133; 101 PostgreSQL/API/adapter tests, atomic issuance/retry checks, live Floci EventBridge/SQS delivery and CI passed. Issue #117 closed. Real catalogue integration was subsequently verified in R04 (merged PR #142); PDF generation subsequently completed in P02 (merged PR #144); browser and AWS integration remain unverified. | R02, M02, C05 | S |
| [x] | U12 | Build doctor note/prescription form using fixtures. Completed in merged PR #118; split notes, prescription editor and medication fields, typed medication names, draft validation and issuance locking. Standalone 62 frontend tests, lint, TypeScript/build, Prettier and CI passed. Issue #115 closed. Real catalogue-linked records integration subsequently completed in R04 (merged PR #142). | F07, F08, C04 | M |
| [x] | U13 | Build patient prescription view using fixtures. Completed in merged PR #120; separate patient panel, summary and details components with Prettier formatting. All 67 frontend tests, lint, TypeScript/build, Prettier and CI passed. Issue #116 closed. Browser checks remain unverified; real records integration subsequently completed in R04 (merged PR #142). | F07, F08, C04 | S |
| [x] | R04 | Connect note/prescription pages to real records APIs. Completed in merged PR #142; issue #141 closed. Real appointment selection, catalogue-linked drafts, note saves, issuance and patient list/details implemented; 74 frontend tests, lint/build and real Floci/five-service HTTP adapter checks passed with synthetic cleanup. Browser/AWS and actual payment/consultation journeys remain unverified. Evidence: `docs/records-frontend.md`. | R02, U12, U13 | M |
| [x] | P01 | Create document service metadata schema and simple prescription, receipt and medical certificate (MC) PDF templates. Completed in merged PR #122; 34 PostgreSQL/PDF tests, migration round-trips, lint/format and CI passed. Issue #121 closed. Live generation/storage subsequently completed in P02 (merged PR #144); downloads remain P03; CJK font support remains a limitation. | F04, C04 | M |
| [x] | P02 | Consume prescription event, generate PDF once and store in private S3. Completed in merged PR #144; issue #128 closed. Implements service-only audited records/name lookups, private-bucket configuration checks, stored-object reuse, inbox/outbox and safe retry/replay. 52 document and 108 records tests plus live Floci pipeline/recovery checks passed. No additional issuance snapshot. Address/registration fields are optional; AWS privacy and downloads remain unverified (Floci limitation #54). Download APIs/UI remain P03/U14. Evidence: `services/document/docs/worker.md`. | P01, R03, F11, M03 | M |
| [x] | P03 | Add authorised document list/download APIs with browser-reachable signed URLs. Completed in merged PR #148; issue #147 closed. Patient/assigned-active-doctor access, current appointment context, durable audits, scoped pagination and SigV4 browser-host URLs implemented. 89 document tests, live Floci/identity/scheduling HTTP checks with isolated synthetic fixtures, lint/format and CI passed. U14 browser UI and real AWS privacy/expiry verification (#54) remain unfinished. Setup/evidence: `services/document/docs/api.md`. | P02, A06 | M |
| [ ] | U14 | Build document list/download UI and connect real document APIs. Assignee: NorbertLoh; status: in progress. Issue #150 / PR #151; implementation and local verification complete, review/merge pending. | F07, P03 | S |

## Week 2-3: delivery, email and messaging

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [x] | M01 | Add shared event envelope validation and SDK endpoint configuration. Completed in merged PR #77. | F03, C05 | S |
| [x] | M02 | Add minimal outbox publisher with retryable send and publication tracking. Completed in merged PR #97; transactional staging, retry/publication tracking and PostgreSQL concurrency checks passed. Issue #96 closed. | F04, F12, M01 | M |
| [x] | M03 | Add SQS consumer helper with acknowledgement, inbox deduplication and retries. Completed in merged PR #99; SQLite/PostgreSQL checks and live Floci consumption, deduplication and failed-job DLQ delivery passed. Issue #98 closed. | F12, M01 | M |
| [x] | M04 | Document and verify one failed job reaching DLQ and operator replay. Completed in merged PR #119; isolated live Floci checks verified three failed receives with rollback, unchanged DLQ content, successful replay and duplicate suppression; lint and CI passed. Issue #113 closed. Operator procedure: `docs/messaging-replay.md`; AWS verification remains unperformed. | M03 | S |
| [x] | D01 | Create fulfilment schema/catalogue and prescription-linked order APIs. Completed in merged PR #131; 59 PostgreSQL/API tests, schema isolation, concurrency/idempotency, access checks, lint and CI passed. Issue #130 closed. Uses the explicitly permitted C04 dispensing fixture; real authenticated records dispensing projection/adapter and pricing/payment integration remain unfinished. | F04, C04, A06 | M |
| [ ] | D02 | Add sandbox delivery quote adapter with expiry and trusted order total. Assignee: NorbertLoh; status: in progress, blocked by unchecked X05 Lalamove sandbox verification. D01 is complete. Claim/blocker: issue #134. | D01, X05 | M |
| [ ] | D03 | Add authorised clinic medicine-ready action. | D01 | S |
| [ ] | D04 | Consume medication-payment event and persist paid state idempotently. | D01, M03, C05 | M |
| [ ] | D05 | Submit one delivery only after paid AND ready; handle uncertain provider outcomes. | D02-D04 | L |
| [ ] | D06 | Add verified callback or documented polling to update delivery status. | D05, X05 | M |
| [ ] | U15 | Build medication order/quote/payment view using fixtures. | F07, F08, C04 | M |
| [ ] | U16 | Build clinic readiness and patient/clinic tracking views using fixtures. | F07, F08, C04 | M |
| [ ] | D07 | Connect fulfilment pages to real APIs and medication checkout. | D06, U15, U16, B06 | M |
| [ ] | N01 | Create notification schema, templates and SES adapter; inspect a local message. | F04, F09, M01 | M |
| [ ] | N02 | Consume booking/document/delivery events; deduplicate sends and record status. | N01, M03, C05 | M |

Service-specific outbox/inbox migrations belong to the service using the helpers. No service writes another service's tables. Fixtures unblock B06 and D01 development; the real order pricing/payment boundary is verified in I03.

## Week 1-3: AWS tasks, individually claimable

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [ ] | W01 | Choose IaC tool; create environment skeleton, cost notes and ignore remote state. | F01, F02 | M |
| [ ] | W02 | Provision network/security groups and HTTP API -> VPC Link -> internal ALB ingress. | W01 | L |
| [ ] | W03 | Provision ECR/ECS skeleton and scoped execution/task roles; deploy health service. | W02, F05 | L |
| [ ] | W04 | Host built frontend on private S3/CloudFront with SPA/API routing separated. | W01, F07 | M |
| [ ] | W05 | Provision dev Cognito public client/callbacks; verify real login/token validation. | W01, A01, A03 | M |
| [ ] | W06 | Provision RDS and service schema/users; document migration task execution. | W02, F04 | M |
| [ ] | W07 | Provision Redis and configure service-only access. | W02 | M |
| [ ] | W08 | Provision private document bucket and synthetic Secrets Manager entries. | W01, F11 | M |
| [ ] | W09 | Provision AWS event rules/queues/DLQs; verify one real delivery. | W01, F12 | M |
| [ ] | W10 | Verify SES demo sender/recipients and one email. | W01, N01 | S |
| [ ] | W11 | Deploy signalling ALB/ECS and TURN; verify HTTPS/WSS cross-network video. | W03, V03, X01 | L |
| [ ] | W12 | Create reusable service deployment command and immutable image tagging. | W03, W06 | M |
| [ ] | W13 | Deploy identity and tenant services; verify AWS login and clinic APIs. | W05, W12, A11 | M |
| [ ] | W14 | Deploy scheduling service; verify availability and appointment APIs. | W07, W12, S07 | M |
| [ ] | W15 | Deploy billing API/workers; configure public verified Stripe callback. | W09, W12, B07 | M |
| [ ] | W16 | Deploy consultation and clinical-record services; verify appointment context. | W12, V04, R04 | M |
| [ ] | W17 | Deploy document API/worker; verify private PDF download. | W08, W09, W12, U14 | M |
| [ ] | W18 | Deploy fulfilment API/worker; configure callbacks/polling and outbound access. | W09, W12, D07 | M |
| [ ] | W19 | Deploy notification worker; verify AWS event produces one email. | W09, W10, W12, N02 | M |
| [ ] | W20 | Publish frontend configuration for deployed routes; verify API errors and auth. | W04, W05, W13-W19 | M |
| [ ] | W21 | Write deploy/reset/log/teardown runbook and budget/log-retention settings. | W12 | M |

Each deployment task includes that service's Dockerfile/commands, environment values, health check and migrations. Keep business services independently deployed. Document controlled migration ordering and avoid migration execution on every replica startup. Deploy skeleton in Week 1; do not leave all AWS work to Week 3.

## Integration gates and Week 4 demo checks

| Done | ID | Task and completion criterion | Depends on | Effort |
| --- | --- | --- | --- | --- |
| [ ] | I01 | Run real local clinic approval -> booking -> Stripe payment -> confirmed appointment. Target end of Week 2. | A11, S05-S07, B04, B07 | M |
| [ ] | I02 | Run actual booked pair -> consultation -> saved prescription -> private PDF. | I01, V04, R04, U14 | M |
| [ ] | I03 | Run actual prescription -> quote -> separate medication payment -> ready -> one delivery. | I02, D07, B06 | M |
| [ ] | I04 | Verify journey events produce booking/document/delivery messages. | I03, N02 | S |
| [ ] | I05 | Run complete patient journey on AWS without DB edits or fabricated success states. Target end of Week 3. | I04, W11, W20 | M |
| [ ] | Q01 | Reject clinic A access to clinic B appointment, record and file; reject wrong roles/tokens. | I05 | M |
| [ ] | Q02 | Verify two competing slot requests cannot both confirm; expired hold releases slot. | S06 | S |
| [ ] | Q03 | Replay payment webhook/delivery job; confirm one effect and demonstrate DLQ replay. | I03, M04 | S |
| [ ] | Q04 | Verify AWS video across networks and reject unrelated participant/file access. | I05 | S |
| [ ] | Q05 | Walk through all four roles; record blockers and create small fix tasks. | I05 | M |
| [ ] | Q06 | Have a different teammate follow fresh local setup/seed/reset instructions. | F14, F16, W21 | M |
| [ ] | E01 | Write presenter handoffs, demo accounts, steps and expected screens. | Q05 | S |
| [ ] | E02 | Capture successful AWS backup video/screenshots before final-day changes. | Q05 | S |
| [ ] | E03 | Write final architecture/local-AWS setup report and explicitly document limitations. | Q01-Q06, W21 | M |
| [ ] | E04 | Record shutdown date/resource owner and keep demo available through assessment. | W21, F01 | S |

Week 4: finish essential checks in the first half; freeze features, rehearse and prepare evidence in the second half. Extensive automated tests, load benchmarks, formal usability studies, premium features and automated refunds are deferred. Record simulated integrations honestly.

## Completion checklist

- [ ] Actual AWS patient journey works with two separate payment purposes and paid+ready delivery gating.
- [ ] All four role views support the journey; two clinics demonstrate tenant separation.
- [ ] Independent service deployments, service-owned migrations and Floci setup are documented.
- [ ] Essential checks and known limitations have brief evidence.
- [ ] Demo script, backup recording and report are ready.
