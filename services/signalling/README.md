# Admitted PeerServer (V03)

Tracks issue #197 / PR #198. This package runs PeerServer 1.0.2 with the X02
pre-registration transport adapted to V02's real consume/check/release APIs.
The runtime image contains only `src`, locked production dependencies and package
metadata. The old `spike` issuer and all test fixtures remain outside the image.

## Local HTTPS/WSS setup

Start the real consultation API and its identity/scheduling/billing dependencies
using `../consultation/ADMISSION.md`. Apply consultation migration 0002 and configure
the four independent service keys. The signalling key below must match
consultation's `SERVICE_SIGNALLING_SECRET`.

From `services/signalling`:

```powershell
Copy-Item .env.example .env
# Set a random SIGNALLING_SECRET of at least 32 bytes in .env.
# Ensure the host consultation API is reachable from Docker at the URL in .env.
docker compose up --build --wait --wait-timeout 90
docker compose cp tls:/data/caddy/pki/authorities/local/root.crt ../../.local/signalling-root.crt
```

Only `https://localhost:8443` is published, bound to loopback. PeerServer's HTTP port
is private to this Compose network. Caddy's internal local CA lives in named
volumes; the command exports its public root certificate. Explicitly trust that
local root in a dedicated browser/test environment when needed; no host trust store
is modified by this setup. Keep CA private keys private. Tests may use a test-only
certificate exception; the real-stack verification also checked the certificate
against the exported root. `docker compose down` stops this isolated stack.

The service-local Caddyfile routes only `/peerjs/*`, POST
`/api/v1/consultation/admissions` (rewritten to `/admissions`) and `/healthz`.
Internal consultation APIs, fixture endpoints and other paths are excluded.
Caddy handles WebSocket upgrades through its [reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
and uses [local TLS](https://caddyserver.com/docs/caddyfile/directives/tls).
Access logs remain disabled; runtime request dumps are suppressed because an
upgrade URI contains the admission credential. Neither Node nor Caddy logs
credentials, bodies or raw socket errors. Never enable unredacted ingress logs.

No root Compose, frontend routing or application UI is changed. V04 must serve
the room from HTTPS and configure its exact origin in `SIGNALLING_ORIGINS`.
The local Compose default allows `https://localhost:8443`; direct Node startup
supports a comma-separated list of exact HTTPS origins. Wildcards are rejected.
`CONSULTATION_URL` is the internal V02 API base; `CONSULTATION_UPSTREAM` is Caddy's
issuer upstream. Docker Desktop uses `host.docker.internal`; Linux Compose adds
the host-gateway mapping. Protect backend host ports and use appropriate bind
addresses so Docker can reach them. This is a service-local development profile.

V04 adds an optional full-application HTTPS entry point using `compose.app.yaml`
and online discovery at POST `/peerjs/counterpart`. See
`../../docs/V04-booked-video.md` for the command, scoped capability contract and
browser verification. The original signalling-only profile retains its allowlist.

## Admission and transport behavior

Request a V02 admission with the user's verified access token:

```javascript
const response = await fetch('/api/v1/consultation/admissions', {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ appointment_id: appointmentId }),
});
if (!response.ok) throw new Error('Admission denied');
const grant = await response.json();
const peer = new Peer(grant.peer_id, {
  host: 'localhost', port: 8443, secure: true, path: '/peerjs',
  key: 'telelink', token: grant.token,
});
```

The upgrade boundary validates path/key, exact Origin, unambiguous query fields
and credential shape. It awaits V02 consumption before invoking WebSocket upgrade
or registering a peer. No client identity, appointment or tenant claim is trusted.
Peer discovery and unauthenticated peer-ID allocation are disabled. Consume
timeouts/failures deny the handshake; consumption is never retried automatically.
If the consume response is lost, request a fresh admission after lease expiry.

V02's returned participant/session/tenant/appointment/peer bindings are retained
only for the socket lifetime. Frames are limited to 64 KiB, serialized per socket
and bounded to 16 queued frames. Source IDs must match the admitted peer.
HEARTBEAT is local; OFFER/ANSWER/CANDIDATE/LEAVE/EXPIRE require an online distinct
participant in the same session, tenant and appointment. Unknown, binary, malformed,
forged-source, offline-target and cross-appointment frames close with code 1008
before PeerServer can route/queue them. Both source and destination leases are
checked through V02 before routing, then checked locally again after the awaits.

An idle eligibility check runs every two seconds. A failed/denied/timed-out check
closes the socket; a separate timer enforces the original lease deadline even
without traffic. No check extends expiry. V02's default 60-second lease means a
fresh admission/peer ID is needed to reconnect after expiry. Automatic PeerJS
reconnect with the old credential is denied. Disconnect/failed upgrade releases
the lease; release is idempotent with at most three bounded attempts. A lost
release recovers at lease expiry. The local routing slot is removed immediately
on denial, before waiting for the close handshake.

The listener bounds pending plus active connections to 100. SIGINT/SIGTERM drains
admitted sockets, rejects new upgrades and exits after up to three seconds; the
container has a five-second stop grace period. One replica is the supported scope:
the live routing map is process-local even though V02 consumption is durable.
Do not scale out until affinity/reconnection and shared routing are proven.

For direct Node use, set the environment variables in `.env.example` explicitly
(Node does not load `.env` itself), then `npm ci --ignore-scripts; npm start`.
The listener defaults to loopback. Production configuration requires an HTTPS
consultation upstream with normal certificate validation. JWT service credentials
use sub `signalling`, issuer `telelink-service:signalling`, audience
`telelink-consultation-admission`, HS256 and a 60-second lifetime. Keys are separate
from Cognito and all other service keys. Container images are pinned by digest.

## Verification and boundaries

```powershell
npm ci --ignore-scripts
npm test
# Explicit test adapter for browser transport checks only:
$env:SIGNALLING_SECRET='v03-test-only-signalling-secret-at-least-32-bytes'
$env:CONSULTATION_URL='http://host.docker.internal:9050'
$env:CONSULTATION_UPSTREAM='host.docker.internal:9050'
docker compose up --build --wait --wait-timeout 90
npx playwright install chromium
npm run test:browser
docker compose down
```

The test fixture binds port 9050 temporarily for container access. It is started
and stopped by Playwright, never by the runtime image or ordinary Compose startup.
Use these fixture environment settings only in an isolated test session. The Node
suite uses `--test-force-exit` after completed tests because the pinned PeerServer
keeps internal maintenance intervals alive; test teardown drains sockets/servers.

Observed locally: 11 Node checks passed; Chromium established a real PeerJS data
channel through the built container and Caddy HTTPS/WSS, exchanged data in both
directions and rejoined with a fresh peer ID. Browser transport tests use an
explicit consultation adapter. An additional real-stack run used V02 plus actual
identity, scheduling and billing apps with restricted PostgreSQL roles, verified
JWKS and synthetic persisted patient/doctor/paid-booking records. HTTPS issuance,
trusted-root WSS registration, OFFER forwarding and replay rejection passed.
Actual identity membership revocation closed the doctor's idle socket; a persisted
billing refund closed the patient's idle socket. Public internal-route attempts
returned 404.

These checks establish local TLS, admission and signalling integration. They do
not establish a new Stripe payment, a full booking journey, application video-room
integration, media termination, independent-network TURN or AWS compatibility.
V04 retains application lifecycle/room integration; RF01 retains cross-network/AWS
evidence. Existing WebRTC media bypasses signalling and is not forcibly stopped
by a signalling lease expiring.
