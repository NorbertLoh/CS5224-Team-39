# V04: booked appointment video

Tracks issue #201 / PR #202. Patient and doctor appointment details now link to
`/<role>/consultation?appointment_id=<UUID>`. The route checks the real scheduling
appointment and current identity before mounting the room. Without a booking ID it
links back to appointments. Clinical records stay pinned to the same appointment.

The link requires the owning patient/assigned doctor, `confirmed` or `in_progress`,
a linked confirmed payment, and the interval from ten minutes before start to the
appointment end. These are navigation hints. Admission independently rechecks
current identity, scheduling, billing and server time. URL roles never grant access.

## Local application entry point

Start identity, scheduling, billing and consultation as in
`services/consultation/ADMISSION.md`; use separate service secrets and migration
0002. Start clinical records, fulfilment and document for the full records workspace.
Set frontend API targets in `apps/web/.env`; `CONSULTATION_API_TARGET` defaults to
loopback 8004. The Vite proxy strips `/api/v1/consultation` and blocks internal
routes. The root Compose configuration is unchanged.

From `apps/web`, run `npm ci`, then `npm run dev -- --host 0.0.0.0`. This makes Vite
reachable from Docker; use this on a trusted development machine. From
`services/signalling`:

```powershell
# .env contains SIGNALLING_SECRET matching consultation and CONSULTATION_URL.
docker compose -f compose.yaml -f compose.app.yaml up --build --wait --wait-timeout 90
docker compose -f compose.yaml -f compose.app.yaml cp tls:/data/caddy/pki/authorities/local/root.crt ../../.local/signalling-root.crt
# Stop this same application stack:
docker compose -f compose.yaml -f compose.app.yaml down
```

Open **https://localhost:8443**. The optional override serves the Vite app/API proxy
and admitted PeerServer from one HTTPS origin. `WEB_UPSTREAM` defaults to
`host.docker.internal:5173`; change it for another Vite port. The original
signalling-only profile remains available without the override. Configure Cognito
callback/logout allowlists for the HTTPS origin and explicitly trust its local CA
in your dedicated development browser as needed. This workflow never changes the
host trust store. Automated local TLS tests may use a test-only certificate exception.

Use a paid booked appointment within its join interval. Open its details and select
**Open video consultation**. Join requests camera/microphone, obtains authenticated
admission and connects WSS with the issued peer/credential. The doctor waits; the
patient discovers and initiates media. Users never enter peer IDs/credentials.
Every rejoin obtains a fresh peer, admission and media configuration. Credentials
remain in memory, except PeerJS's required WebSocket token parameter; redact it
from ingress logs. The room cleans up media on leave, expiry, revocation or unmount.

## Discovery and ICE

POST `/peerjs/counterpart` accepts exactly `{peer_id, token}` in the body. This is
a scoped bearer capability for the caller's consumed, online admission. The
request must have an allowed HTTPS Origin. The server checks the caller's real
admission, selects a live distinct participant in the same session/tenant/appointment,
checks that target's current eligibility and rechecks both local live slots after
awaiting upstream. It returns `{peer_id: UUID|null}`. Offline, released, expired,
rotated and unrelated peers are excluded. Bodies, credentials and parser errors
are not reflected/logged. Discovery uses the configured upstream timeout,
connection limit and 1 KiB body limit. Existing frame isolation still applies.

Admission includes `ice_servers` and `relay_only`. For coturn REST auth configure
consultation's JSON `SERVICE_TURN_URLS` list and an independent `SERVICE_TURN_SECRET`
of at least 32 bytes matching coturn. `SERVICE_RELAY_ONLY=true` requires TURN.
Credentials use the issued peer ID and admission expiry with coturn's HMAC-SHA1
REST format. The shared secret stays on the server. Without configured TURN the
ICE list is empty, suitable only where direct connectivity succeeds. Reachable
TURN infrastructure is still required for restrictive networks.

## Doctor lifecycle

POST `/api/v1/consultation/appointments/{id}/start` and `/complete` require the
currently assigned active doctor, user access token, trusted appointment and
successful linked payment. Explicit doctor actions start clinical writing and
complete the appointment. Joining/leaving media alone never changes its lifecycle.
Start is permitted from appointment start; scheduling's `in_progress` status gates
clinical writes. Completion denies future admission. Clients clean up when their
appointment refresh or WSS eligibility check observes completion.

Local lifecycle intent commits before the scheduling handoff. These are separate
transactions. On failure refresh and retry the same action: it reads scheduling's
current state and skips an already applied transition. A locally completed session
denies admission even while scheduling is unavailable. There is no background
reconciler: retry is required if a handoff did not apply. Terminal appointments
are never reopened. A start retry is still subject to the original start window
if the local start was never committed. An uncertain handoff must be resolved
before attempting a different lifecycle action.

## Verification

Run `npm run lint`, `npm run typecheck` and `npm run build` from `apps/web`; run `npm test`
from `services/signalling`. Consultation uses the disposable PostgreSQL setup,
`python -m pytest -q`, `python -m ruff check .` and `python -m ruff format --check .`
described in its README. RF04 removed the frontend test harness; current frontend
scripts do not provide `npm test`. Historical proxy/browser checks below were
recorded in PR #202 and do not represent a new run.

Synthetic persisted paid bookings and signed test identities establish local
integration, not a new hosted Stripe payment or a complete patient booking flow.
AWS, independent-network/physical-device observations and RF01 remain separate.

### Observed results, 19 October 2026

- 111 frontend tests, ESLint and production typecheck/build passed.
- 110 consultation tests passed against disposable PostgreSQL, plus Ruff checks.
- 12 signalling checks passed, including live scoped discovery and parser privacy.
- CI passed frontend, consultation, backend lint, signalling and forced-TURN video.
- Two isolated Chromium contexts loaded the production application through the
  optional HTTPS proxy, using signed, scoped synthetic identities and actual
  identity/scheduling/billing/consultation apps with persisted synthetic paid
  appointments. Both roles navigated from appointment details; an unrelated user
  was denied. Real admission consumption and live counterpart discovery connected
  bidirectional audio/video RTP. Leaving stopped tracks/connections; rejoining
  issued two distinct fresh peer IDs per participant and restored media. Doctor
  start/completion updated actual scheduling and both rooms cleaned up on completion.

The browser used fake camera/microphone sources, a local certificate exception and
HTTP/1.1 for the loopback TLS test. Ancillary tenant, clinical-record and document
services were not started in this run; their panels reported unavailable APIs.
No clinical save/download, new hosted payment, full booking flow, physical-device
or AWS result is claimed by this browser check. The isolated app/API processes and
signalling Compose project were stopped after verification.
