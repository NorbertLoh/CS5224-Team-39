# X02: appointment-bound signalling admission spike

Tracks [issue #156](https://github.com/NorbertLoh/CS5224-Team-39/issues/156) and
[PR #157](https://github.com/NorbertLoh/CS5224-Team-39/pull/157). This is a local,
fixture-based feasibility spike using PeerServer 1.0.2, PeerJS 1.5.5 and ws 8.22.0.
It does not implement the consultation service or complete V01-V04.

## Run and reproduce

From `services/signalling/spike` with Node >=22.12:

```powershell
npm ci
npm run start:admission
# Separate terminal:
npm test
npm run test:browser
```

The admission harness always binds to `127.0.0.1` (default port 9002;
`X02_PORT` overrides the port). It is deliberately separate from X01's unauthenticated
port 9000. Never route public traffic to the X01 server or deploy the fixture issuer.
Playwright starts both servers and uses bundled Chromium (`npx playwright install chromium`).
`X02_TTL_SECONDS` sets the admission lifetime (1-300 seconds, default 60).

For manual protocol inspection, POST `/fixture/admissions` with JSON
`{"appointmentId":"appointment-a"}` and `Authorization: Bearer fixture-patient-a`
or `Bearer fixture-doctor-a`. The response supplies `peerId`, `token`, `subject`,
`appointmentId` and `expiresAt` (Unix milliseconds). These public fixture bearer
strings select synthetic identities; they are **not real authentication**.
The issuer ignores body-supplied identity/peer IDs. `appointment-b` belongs to
`patient-b`/`doctor-b`; `unrelated` belongs to neither. Unpaid, cancelled, early,
late and unknown appointments are denied.

Use the supplied identity and credential with the self-hosted client:

```javascript
const peer = new Peer(grant.peerId, {
  host: '127.0.0.1', port: 9002, path: '/peerjs', key: 'x02',
  token: grant.token, secure: false, config: { iceServers: [] },
});
```

Both participants must connect before exchanging signalling. Their peer IDs can
be exchanged manually for this spike; authenticated peer discovery belongs to
V02/V04. Peer discovery remains disabled. The root page only loads the local
PeerJS bundle for browser automation/console inspection; there is no new app UI.

## Enforcement and reconnect contract

The fixture issuer checks participant membership, paid/booked state and join
window. It creates an unpredictable, opaque 256-bit credential with server-side
appointment/subject/peer bindings. The lease ends at the earlier of its short
lifetime and the appointment's join-window end. No client claim is trusted.

The transport owns HTTP `upgrade` handling through PeerServer's
`createWebSocketServer` option. It checks path, key, unambiguous ID/token query
parameters and consumes the credential atomically **before** calling
`ws.handleUpgrade` or exposing a socket to PeerServer. Rejected upgrades return
403 and never register a peer. A consumed credential cannot reconnect or open a
second socket. A malformed handshake also consumes it; request a new one.
Only one active socket per participant/appointment is admitted.

A small EventEmitter socket bridge forwards only validated frames to PeerServer;
it implements the `on`, `send` and `close` surface used by the pinned version.
No PeerServer internals or installed dependency files are modified. Each frame
checks the source lease and destination's active lease, appointment and distinct
participant. OFFER, ANSWER, CANDIDATE, LEAVE and EXPIRE require an admitted online
counterpart in the same appointment. HEARTBEAT is local and must have no
destination. Supplied source IDs must match the admitted identity. Unknown,
malformed, binary, offline-target and cross-appointment frames fail closed with
WebSocket code 1008, before PeerServer can route or queue them. Frames are capped
at 64 KiB. An expiry timer closes idle sockets too; checks on every frame cover
timer delays. A denied socket loses its routing slot immediately.

Disconnect releases the participant slot. Rejoin requires a fresh admission and
a fresh random peer ID; applications must explicitly reacquire admission instead
of relying on PeerJS's automatic reconnect using its old token. In-memory grants
and sessions reset on server restart. Pending grants are pruned on issuance and
bounded at 100. This is a single-process/single-replica spike.

## Why the default hooks are insufficient

PeerServer's `key` identifies its namespace. Its ordinary `token` compares a
reconnecting connection against an existing peer; neither proves appointment
membership. The public `connection` event runs after registration and `OPEN`.
The public `message` event observes a frame and does not cancel routing. The
admission transport therefore gates both earlier boundaries. See pinned upstream
[connection handling](https://github.com/peers/peerjs-server/blob/v1.0.2/src/services/webSocketServer/index.ts)
and [message dispatch](https://github.com/peers/peerjs-server/blob/v1.0.2/src/instance.ts),
plus [ws upgrade API](https://github.com/websockets/ws/blob/8.22.0/doc/ws.md#serverhandleupgraderequest-socket-head-callback).
Re-run the wire and browser checks when upgrading either library; the bridge is
intentionally limited to the tested PeerServer version's socket surface.

## Integration boundaries

V02 must replace the fixture issuer with verified identity and trusted current
appointment, participant, payment and join-window context; reject missing or
unavailable context. The spike does not call real scheduling/payment services.
Production grant storage/replay decisions must remain atomic if replicas are
ever added; this implementation is in memory. V03 must expose only the gated
HTTPS/WSS ingress and redact query credentials from access/error logs. The
fixture server records neither credentials nor signalling payloads.

Lease expiry stops signalling. It does not terminate an established WebRTC data
or media connection; that path bypasses PeerServer. UI/session lifecycle and any
stronger media termination policy remain consultation integration work. RF01
and W11 retain independent-network, TLS and AWS verification; X02 establishes
local signalling admission only.

## Observed results

Local verification on 17 October 2026 (Singapore), Windows, Node 24.13.0,
Playwright 1.64.1 Chromium:

- `npm test`: 11 passed (including six real-server admission subtests and all
  three existing X01 checks). Covers fixture eligibility, handshake rejection,
  replay, identity binding, signalling isolation, malformed input, expiry and rejoin.
- The browser admission check passed: actual PeerJS data-channel offer/answer/ICE
  exchange, echoed data in both directions and fresh-credential rejoin. Fake camera
  and microphone permission makes local host ICE candidates available on Windows;
  no real devices, independent networks or TURN are claimed by this check.
- Full `npm run test:browser`: 3 passed, 1 skipped. Existing X01 media/control/rejoin
  and missing-TURN validation checks passed. The existing invalid-TURN-credential
  check was skipped because no actual TURN settings were supplied for this run.

The existing CI workflow runs the Node suite and all browser checks. Final CI
results are linked from the PR. Keep issue #156 In progress and X02 unchecked
until the PR merges.
