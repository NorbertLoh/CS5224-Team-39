# X01: self-hosted PeerJS / TURN feasibility spike

Continuation of [issue #56](https://github.com/NorbertLoh/CS5224-Team-39/issues/56)
and [draft PR #57](https://github.com/NorbertLoh/CS5224-Team-39/pull/57).
This standalone harness uses synthetic data and consenting testers.
Appointment admission is the [X02 fixture spike](ADMISSION.md), production packaging is V03/W11, and frontend
integration is U11/V04. See [observed results](RESULTS.md).

Accepted scope (16 October 2026): local two-browser calls and actual local TURN
checks satisfy X01. AWS cross-network verification is deferred to refinement
[RF01 / #155](https://github.com/NorbertLoh/CS5224-Team-39/issues/155); it is not a
merge blocker for X01 and does not complete the AWS integration gates.

## Signalling versus media

Node serves the page, the locally installed PeerJS client and PeerServer on one
origin. There is no PeerJS cloud fallback. PeerServer exchanges connection offers
and ICE candidates over WebSocket; it does not carry audio/video. WebRTC carries
encrypted media directly, or through coturn when direct routing fails. Connected
signalling alone proves no media path. There is no default public STUN service.
Forced relay sets `iceTransportPolicy: 'relay'`; TURN failure cannot silently
fall back to a direct connection.

## Local smoke check (Windows or Linux, Node 24)

From `services/signalling/spike`:

```powershell
npm ci
npm test
npx playwright install chromium
npm run test:browser
npm start
```

Open `http://127.0.0.1:9000` in two windows, click **Start** in both, exchange
peer IDs and click **Call** once. Incoming calls are answered automatically while
started. Use headphones and verify speech and moving video at both ends. Try
mute, camera disable, hang-up, Leave and Start again. Leave releases camera/mic;
hang-up keeps them ready. Settings apply on Start, so Leave before changing them.

Browser tests use fake media and check received frames, bidirectional audio/video
bytes, controls, evidence export and rejoin. The actual-TURN negative test is
skipped unless TURN environment variables are supplied (below). Fake media does
not prove human audibility or two-network connectivity. HTTP tests run PeerServer
in a child process because its recurring timers have no public shutdown API.
The ignored `test-results/report.json` includes the caller's evidence attachment;
each browser test run replaces that report.

## Prepare an internet-reachable test host

A test host is a computer both testers can reach over the internet. Use an
existing approved Linux VM with a public IPv4 address, DNS names such as
`call.example.com` and `turn.example.com` pointing to it, and certificates trusted
by both browsers. This spike does not provision infrastructure. Its coturn
Compose file uses Linux host networking; Docker Desktop networking is not
evidence of a public deployment.

Install Node 24 and Docker Compose; copy this directory and run
`npm ci --omit=dev`. Store the call hostname's certificate chain and key outside
Git, restrict key permissions, and keep certificates renewed. Start Node with:

```sh
export SPIKE_HOST=0.0.0.0
export SPIKE_PORT=9000
export SPIKE_TLS_CERT=/secure/call/fullchain.pem
export SPIKE_TLS_KEY=/secure/call/privkey.pem
npm start
```

Open `https://call.example.com:9000`. Node refuses non-loopback HTTP: browsers
require a secure context for camera access. TLS also protects WSS under `/peerjs`.
Never bypass certificate warnings for verification. No reverse proxy is needed;
if using an existing proxy, preserve `/peerjs` and forward WebSocket upgrades.

Restrict port 9000 to the two testers' source IPs at the host/cloud firewall.
The `x01` key is a protocol key, **not authentication**. This spike has no
appointment admission; discovery is disabled and the client cap is ten. Run it
only for the verification window, then stop it.

## Coturn setup

On the Linux host, from this directory:

```sh
mkdir -p .local/tls
chmod 700 .local .local/tls
cp turnserver.conf.example .local/turnserver.conf
chmod 600 .local/turnserver.conf
node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
```

Edit the ignored `.local/turnserver.conf`. Replace the secret placeholder with
the generated random value, replace `external-ip`, and set `realm`/`server-name`
to the TURN hostname. Copy that hostname's trusted full certificate chain and
private key into `.local/tls/fullchain.pem` and `.local/tls/privkey.pem`. Restrict
private key access to the operator/container and ensure mounted files are readable
by coturn. Do not start with placeholders or use the example as a real credential.

Set `external-ip` to the host's public address; behind 1:1 NAT, use
`external-ip=PUBLIC_IP/PRIVATE_IP`. Preserve relay port numbers through NAT.
CGNAT, TCP-only tunnels and HTTP load balancers do not replace reachable UDP
relay ports. The example denies private/loopback relay destinations and targets
internet clients using public relay candidates.

| Host port | Purpose | Firewall / forwarding |
| --- | --- | --- |
| TCP 9000 | Harness HTTPS and PeerServer WSS | Two testers only |
| UDP 3478 | TURN over UDP | Testers; allow replies |
| TCP 3478 | TURN over TCP | Testers; allow replies |
| TCP 5349 | TURN over TLS | Testers; allow replies |
| UDP 49160–49179 | Media relay allocations | Reachable by peers/other TURN allocations; preserve port mapping |

Allow outgoing UDP media and stateful return traffic too. Two allocations on this
host must reach each other through its public IP, including NAT hairpin routing
where applicable. The small relay range, quotas and bandwidth cap support two
testers, not capacity planning. `no-tcp-relay` disables RFC 6062 TCP peer
allocations; it does not disable clients connecting to TURN over TCP/TLS.
WebRTC relay allocations here still use UDP. DTLS is disabled; TCP TLS remains
enabled. TCP-443-only networks would need a separately arranged TURN listener
on 443; this setup does not prove that fallback.

```sh
docker compose -f compose.turn.yaml config --quiet
docker compose -f compose.turn.yaml up -d
docker compose -f compose.turn.yaml logs --tail 80 turn
```

The image is pinned by version and multi-platform digest. Check for configuration
and certificate errors. Use `use-auth-secret` exclusively; do not add static users
or `no-auth`.

## Expiring credentials

Set `TURN_SHARED_SECRET` in the operator's environment to the same secret as
coturn's ignored configuration, without writing it into chat or shell history.
Then generate separate short-lived browser credentials:

```sh
npm run credentials -- tester-a 600
npm run credentials -- tester-b 600
```

Output contains a username, credential and expiry time, not the signing secret.
Transfer privately to each tester. Keep the host clock synchronised. Default TTL
is ten minutes (allowed: 60–3600 seconds). Expiry limits authorisation/refresh;
it does not forcibly terminate an existing allocation immediately. Leave and mint
fresh credentials between runs. Never put the signing secret in the browser,
`VITE_*`, Git, screenshots or evidence. The page uses no browser storage for
credentials and clears the credential input after Start.

Enter the temporary credentials and these URLs, one per line, for normal ICE:

```text
turn:turn.example.com:3478?transport=udp
turn:turn.example.com:3478?transport=tcp
turns:turn.example.com:5349?transport=tcp
```

## Deferred AWS two-network verification (RF01)

Use a desktop on Wi-Fi and another device on cellular data with Wi-Fi off, or two
independently routed networks. Two tabs, browsers or containers on one host do
not qualify. Enter non-identifying network labels in the page.

1. **Normal ICE:** supply all URLs, leave Force TURN off, Start both and call.
   Observe at least 30 seconds of two-way speech and moving video. A direct or
   relayed selected pair is valid; record which was selected.
2. **Forced UDP:** Leave both; supply only the UDP URL, fresh credentials and
   Force TURN on at both ends. Repeat. Both exported selected pairs must have
   local `candidateType: relay`; audio/video RTP counters must increase in both
   directions. Merely gathering a relay candidate is insufficient.
3. **Forced TCP and TLS:** repeat separately with only the TCP URL, then only
   the `turns:` URL. Record `relayProtocol` when exposed by the browser. Untested
   transports remain unverified.
4. **Failure:** attempt new forced-relay calls using invalid and expired
   credentials. They must not establish media or select a direct pair. Check
   coturn's rejection logs; the initial TURN 401 challenge alone is normal.
5. Verify mute/unmute, camera disable/enable, hang-up, Leave/rejoin and resumed
   media. Also record permission denial and stopping/restarting signalling.
6. Download evidence JSON at both ends **before** starting the next run. Record
   date/time, browser/OS, network types, duration and human audio/video observations
   in [RESULTS.md](RESULTS.md). Retain matching JSON as reviewed issue/PR attachments.

Evidence retains the last 600 one-second samples and 100 events, with call
numbers. It omits raw ICE addresses, peer IDs, SDP, TURN URLs and credentials.
Review labels and external screenshots/logs before sharing: raw coturn and
browser ICE diagnostics may contain IP addresses or temporary usernames.
Statistics prove neither speech audibility nor network independence.

Keep X01 unchecked and #56 In progress until PR #57 is merged. The local criteria
are met; record the real AWS normal/forced-relay observations under RF01 / #155
when AWS testing resumes. Share that evidence with W11/Q04.

To automate against an actual coturn instance, set `SPIKE_TEST_TURN_URL` to one
URL and set `SPIKE_TEST_TURN_USERNAME`/`SPIKE_TEST_TURN_CREDENTIAL` in the test
process environment, then run `npm run test:browser` for each transport. Tests
require selected relay candidates and bidirectional audio/video bytes and reject
invalid credentials. They still use fake media on one host. Do not commit test
environment variables or temporary credentials.

## Troubleshooting and cleanup

- No camera: use localhost/trusted HTTPS; grant browser/OS permission and close
  other applications holding the device. Start can be retried after denial.
- No peer ID: check `/healthz`, `/peerjs/x01/id`, WSS upgrade, certificate/DNS,
  firewall source rules and Node logs. Signalling success is not a TURN test.
- No relay: check URL, listener transport, expiry, clock, matching signing
  secret and coturn logs.
- Relay selected but no media: check `external-ip`, relay UDP ports, NAT port
  preservation, hairpin routing, outgoing traffic and received RTP counters.
- Media but no sound: inspect playback, device mute and headphones. Fake media
  tests cannot verify human speech.
- Signalling disconnected: Leave/Start for a new peer ID, then call again.
  Appointment admission/reconnect policy belongs to later tasks.

Stop Node with Ctrl+C; run `docker compose -f compose.turn.yaml down`. Remove
temporary firewall openings, retire credentials and rotate exposed secrets.
Private configuration and keys stay ignored under `.local`.

## References

- [PeerJS media calls](https://peerjs.com/client/getting-started)
- [Peer options and ICE configuration](https://peerjs.com/client/api/peer)
- [PeerServer Express integration](https://github.com/peers/peerjs-server#combining-with-existing-express-app)
- [Coturn configuration and TURN REST authentication](https://github.com/coturn/coturn/blob/master/examples/etc/turnserver.conf)
- [Official coturn Docker setup](https://github.com/coturn/coturn/tree/master/docker/coturn)
