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
call's metadata establishes identity.

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

From `apps/web`, run `npm ci`, `npm run lint` and `npm run build`.
For live admission, discovery, media and doctor lifecycle setup, use
[the booked-video guide](../../../../../docs/V04-booked-video.md).
Historical automated browser/TURN results remain recorded in PR #199 and that
guide; the frontend test harness and its CI workflow were removed in RF04.
Independent-network, physical-device and AWS observations remain RF01.
