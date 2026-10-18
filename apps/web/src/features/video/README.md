# Video room (U11)

`VideoRoom` supplies patient call-only and doctor call-plus-records layouts. It
supports real PeerJS 1.5.5 audio/video when given a `RoomConnection` adapter. The
role-protected `/patient/consultation` and `/doctor/consultation` routes use
`BookedConsultation` with real appointment admission and scoped live discovery.
Choose a booking in appointment details; a route without an ID links back there.
No manual peer-ID/token fields or fixture authentication are added to production.

## Adapter boundary

Pass a stable `connection` prop, and key the room by appointment and user so
switching context unmounts the previous call. Its contract is in `connection.ts`:

- `signalling`: trusted WSS host/port/path/key, with `secure: true`.
- `acquire(signal)`: authenticated fresh admission for the selected appointment;
  returns server-issued `peerId`, opaque `token`, absolute `expiresAt`, current
  `iceServers` and optional `relayOnly`. Fetch fresh TURN credentials here; never
  persist credentials or put them into URLs other than PeerJS's required token.
- `counterpart(admission, signal)`: authorized discovery of the other participant's
  currently registered peer, or null while waiting. It must never return an
  unrelated, offline or stale peer. Respect cancellation and bound HTTP timeouts.

V02/V03 provide admission enforcement and signalling. V04 supplies the real
adapter, scoped discovery, booking navigation and explicit doctor start/complete
actions. Setup: `docs/V04-booked-video.md`. Neither a URL role nor an incoming
call's metadata establishes identity. Admission fixtures in the browser tests do
not complete V04 or a real patient booking/payment journey.

## Room behavior

Join requests devices through a user gesture, then fresh admission. The patient
initiates media after discovery; the doctor answers only the resolved counterpart.
Media uses max-bundle ICE, configured TURN and an optional relay-only policy that
fails if no TURN server exists. There is no public STUN/TURN credential default.
Remote video includes audio, a local muted preview and a playback button if browser
autoplay is blocked. Camera and microphone controls enable/disable outgoing tracks.

Leave, Escape, route unmount, device loss, connection failure, signalling loss and
lease expiry close the PeerJS/media connections and stop local/remote tracks.
There is no automatic reconnect with consumed credentials. Rejoin acquires a new
stream, peer ID, admission and TURN configuration. Cancellation prevents late
permission/admission/library responses from reopening a departed call. Admission
and peer startup, plus media negotiation, each have bounded 15-second waits.

The expanded room traps keyboard focus, restores focus on leave/disconnect, and
keeps the doctor workspace mounted so unsaved notes survive call transitions.
Desktop uses side-by-side panels; mobile stacks them without horizontal overflow.
Booked rooms pin records to the selected appointment. Records retain their own
authorization; joining
video never independently grants clinical write access. Saved records survive
reload; unsaved edits are discarded by navigation or changing records context.
Media is not recorded. PeerJS debugging is disabled; errors shown to users never
include raw provider errors, credentials, SDP or ICE addresses.

## Verification

From `apps/web`:

```powershell
npm ci
npm test
npm run lint
npm run build
# Explicit isolated browser adapters; not application authentication:
$env:SIGNALLING_SECRET='v03-test-only-signalling-secret-at-least-32-bytes'
$env:CONSULTATION_URL='http://host.docker.internal:9050'
$env:CONSULTATION_UPSTREAM='host.docker.internal:9050'
docker compose -f ../../services/signalling/compose.yaml -f tests/browser/compose.yaml up --build --wait --wait-timeout 90
npx playwright install chromium
npx playwright test --config playwright.video.config.mjs
node tests/browser/turn.mjs
docker compose -f ../../services/signalling/compose.yaml -f tests/browser/compose.yaml down
```

The test-only HTML entry is outside the production build. Playwright starts Vite
on 5174 and explicit fixture APIs on 9050/9051 for Docker access. A test-only Caddy
configuration serves that harness through localhost HTTPS/WSS; ordinary production
signalling routing remains unchanged. Fixtures and synthetic record caches verify
room behavior, not backend integration. Do not use the test Compose override for
normal development/deployment.

The TURN helper creates a fresh temporary HMAC key and 15-minute credentials,
starts coturn bound strictly to loopback with host networking and no published
ports, and removes its container/config afterward. Docker Desktop needs host
networking support; Linux CI uses native host networking. It tests forced UDP and
TCP relay with selected-candidate and bidirectional audio/video RTP assertions.
No host certificate trust is changed by these tests.

Local checks: 107 frontend tests, lint and production build passed. Three direct
Chromium scenarios passed: actual two-way audio/video RTP/playback; controls,
leave/rejoin and doctor note retention; revocation and expiry cleanup; permission
denial, device loss, mobile layout and navigation. Separate lifecycle regression
checks cover cancellation races, late PeerJS creation, verified incoming-call
answer order and forced-relay validation. TURN/CI results are recorded in PR #199.
Independent-network, physical-device and AWS observations remain RF01; application
admission/booking/clinical lifecycle integration is documented in `docs/V04-booked-video.md`.
