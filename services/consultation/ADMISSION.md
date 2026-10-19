# V02: consultation admission

Tracks issue #195 / PR #196. Service-local routes below omit the public
`/api/v1/consultation` prefix; ingress must strip it. No shared Compose/proxy or
signalling configuration is changed by this task.

V04 extends the grant with fresh `ice_servers` / `relay_only` and adds authenticated
doctor start/complete actions. See `../../docs/V04-booked-video.md` for retry
semantics, configuration and application HTTPS setup. Discovery uses signalling's
online map; public clients never call internal lease APIs.

## API

| Route | Authentication | Body/result |
| --- | --- | --- |
| POST `/admissions` | Verified Cognito access token and fresh identity `/me` lookup | `{ "appointment_id": "UUID" }`; 201 grant |
| POST `/internal/admissions/consume` | Signalling service JWT | `{ "token": "opaque credential", "peer_id": "UUID" }`; 200 lease, single use |
| POST `/internal/admissions/check` | Signalling service JWT | Same body; 200 only for an active consumed lease |
| POST `/internal/admissions/release` | Signalling service JWT | Same body; 204, repeatable for the same consumed lease |

A grant contains `session_id`, `tenant_id`, `appointment_id`, `subject_id`,
server-generated random `peer_id`, UTC RFC3339 `expires_at` and opaque 256-bit
`token`. Consume/check responses omit `token`. Clients cannot submit tenant,
participant, peer, payment truth, timestamps or roles to the issuer; extra fields
are 422. Responses/errors are `Cache-Control: no-store`. Service logs use route
templates and do not include bodies, credentials, query strings or peer IDs.
Run with access logging disabled (`python -m app` does this); upstream ingress must
also redact credentials and must exclude `/internal/*` from public ingress.

Each issuance reads scheduling's actual appointment through a separately
authenticated internal API, asks identity for a current `consultation.join`
decision and reads the linked payment from billing. Only the owning patient with
patient role or assigned active member doctor is admitted. Admin metadata access
does not grant video access. Appointment state must be `confirmed`/`in_progress`,
payment resolution `confirmed`, and a linked payment must be consultation-purpose,
`succeeded`, resolution `none`, with matching appointment/tenant/patient/ID and
exact trusted SGD amount. Missing, denied, malformed or unavailable context fails
closed; no fixture path or authorization bypass exists in the running API.

The V01 join interval is `[starts_at - 10 minutes, ends_at)` for non-completed
sessions. Admission does not start/end a session or mutate scheduling. Issuance
checks current context again after acquiring its parent session lock. Consume
and check re-read current scheduling/identity/billing data under that lock, then
recheck server time after the upstream calls. Cross-service reads are not an
atomic distributed transaction; revocation after a successful check is observed
by the next check/lease expiry.

## Replay, bounded state and V03 boundary

Migration `0002` adds one lease row per session/participant, with a tenant-bound
foreign key. Only a SHA-256 token digest is stored. Issuing again rotates an
unused pending credential. An unexpired consumed/unreleased lease rejects a
second issuance with 409 `participant_connected`. Consuming is serialized on the
parent session, binds the exact generated peer ID and succeeds once, including
across API processes/restarts. Expired or released leases cannot be consumed or
checked. Rejoin requires a new token and a new peer ID. Releasing a stale rotated
token cannot release the replacement connection. A crash can leave a slot claimed
only until the original lease expires; default TTL 60 seconds, configurable 1-300,
capped at appointment end. It is never extended by consume/check.

V03 must replace X02's fixture issuer/store with this HTTP boundary, await consume
**before** websocket upgrade/PeerServer registration, and close the socket if
upgrade fails after consumption. Call release on disconnect; a failed release
can be retried, otherwise wait for expiry. Retain server-issued bindings locally
for frame source/destination isolation and allow only distinct participants in
the same tenant/appointment. Call check for current eligibility, fail closed on
errors and close sockets at `expires_at` even when idle. Never cache a lease past
its deadline. Peer discovery remains an authenticated V04 concern.

X02's wire options accept `new Peer(grant.peer_id, { token: grant.token, ... })`.
Its fixture helper uses camelCase fields; V03 must map the snake_case HTTP lease
to its internal `peerId`, `subject`, `appointmentId`, `expiresAt` (Unix milliseconds)
without trusting client claims. This task does not change or deploy the X02
server and does not claim actual gated WSS/PeerJS integration. Lease expiry/check
does not directly terminate established WebRTC media; V04 retains that concern.

## Configuration and launch

Install dependencies/migrate as in README.md, copy `.env.example` to `.env`, and
set Cognito issuer/JWKS/public client plus identity, scheduling and billing URLs.
Use four different random service secrets (at least 32 bytes):

| Consultation setting | Matching peer setting | JWT issuer/sub and audience |
| --- | --- | --- |
| `SERVICE_IDENTITY_SECRET` | identity `SERVICE_CONSULTATION_SECRET` | consultation / `telelink-identity-consultation` |
| `SERVICE_SCHEDULING_SECRET` | scheduling `SERVICE_CONSULTATION_SECRET` (existing S04 key) | consultation / `telelink-scheduling-consultation` |
| `SERVICE_BILLING_SECRET` | billing `SERVICE_CONSULTATION_SECRET` | consultation / `telelink-billing-consultation` |
| `SERVICE_SIGNALLING_SECRET` | V03 consumer's matching key | signalling / `telelink-consultation-admission` |

Service JWTs use HS256, `iss=telelink-service:<caller>`, `sub=<caller>`, the exact
audience above, integer `iat`/`exp` and lifetime at most 300 seconds. Shared helper
`service_token` issues 60-second credentials. Keys are separate from Cognito and
each service's other keys. Consultation credentials cannot request other identity
actions, medication payment reads or fulfilment payment mutations. Scheduling's
new GET `/internal/appointments/{id}` uses the existing consultation credential.

From this service directory, `python -m app` starts on loopback port 8004. Run
Alembic separately before startup. `/health/ready` requires migration `0002`,
all upstream URLs, access-token configuration and the four service keys; readiness
does not establish remote service availability. Outside local/test, upstream
URLs require HTTPS and the common settings require AWS Cognito issuer/JWKS.

## Verification and limits

Local Python 3.10 / PostgreSQL 18: 99 consultation tests passed, using actual signed
JWT verification, real PostgreSQL, and explicitly mocked upstream HTTP transports.
Those tests cover current role/state/payment gates, isolation, replay, peer
binding, lease rotation/release/rejoin, concurrent consume/issuance, time boundaries,
completed sessions, safe errors and migration/model parity. Supporting identity,
scheduling and billing tests exercise the actual new service credential scopes.

A separate local loopback run launched all four real apps with restricted database
roles, real JWKS verification and synthetic persisted patient/doctor/booking/payment
records. Patient/doctor issuance and consumption, unrelated-user denial, wrong-peer
rejection, replay, duplicate slot prevention, release/rejoin, actual identity
membership revocation and a persisted billing refund all passed through real HTTP
adapters. This proves local service reads and enforcement with synthetic data; no
new hosted Stripe payment, end-to-end booking, PeerServer/browser, TURN, TLS or AWS
verification is claimed. I01/V03/V04/RF01 remain separate integration gates.
