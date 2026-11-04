# RF29 consultation signalling

PostgreSQL assigns one signalling task to each consultation. The consultation
service locks the session row while it selects or replaces an owner, so concurrent
doctor and patient requests receive the same assignment. Each task registers a
private address and a boot identity, renews its lease every three seconds, and
expires after 30 seconds by default. Admission consumption and ongoing checks
require the assigned task, current assignment version and existing participant,
tenant, appointment, payment and time-window checks.

The admission response returns a same-origin `/peerjs/nodes/<id>` path. Either
signalling task can receive the WebSocket or counterpart request from the load
balancer. If a different task owns the room, the entry task forwards the request
over the private network to the registered owner. Admission credentials and
WebSockets stay within the existing signalling path. Node addresses are restricted
to configured literal IPv4 addresses and the signalling port. PostgreSQL stores
only assignment metadata and credential hashes. Redis is unnecessary for this flow.

When an owner disappears, a new admission waits for the expired lease and a healthy
replacement. The old grant fails even if its original expiry is still in the future.
The browser requests a fresh grant, rebuilds its PeerJS connection and reuses its
local media tracks. Transient failures retry with jittered delays up to 30 seconds
between attempts and a 12-hour recovery limit. A browser can suspend a background
tab, so recovery runs when it can execute again. Access denial, leaving, completion
or closing the room stops recovery. RF30 adds authenticated renewal of active
leases while keeping the same peer and media connection. Join credentials remain
single-use. Renewal requires current eligibility and the same room owner.
The active deadline defaults to 60 seconds and the fixed call/TURN deadline to
12 hours. Expiry without renewal uses fresh-admission recovery. See the
[admission contract](../services/consultation/ADMISSION.md) for relay lifetime and
configuration details.

## Deployment

1. Run consultation's `alembic upgrade head` once using the schema owner. Migration
   `0004` adds room assignments and `0005` adds active lease renewal. Deploy the matching
   consultation, signalling and frontend builds together. Earlier frontend builds
   use the singleton path and cannot connect to a matchmaker-enabled room.
2. The managed Singapore profile enables matching on both services, scopes node
   routes to the private subnets and grants signalling tasks ECS task protection.
   Keep `min_tasks` and `max_tasks` at `1` for the demo. The capacity-two overlay
   uses the same configuration with a second task. Update the image digests and
   run the migration before enabling the new tasks.
3. For local opt-in, set `SERVICE_SIGNALLING_MATCHMAKER=true` on consultation and
   `SIGNALLING_MATCHMAKER=true` on each signalling process. Set
   `SIGNALLING_INTERNAL_URL` to each process's reachable private IPv4 address and
   port, then allow that network and port with `SERVICE_SIGNALLING_NETWORKS` and
   `SERVICE_SIGNALLING_INTERNAL_PORT`. The allowlist defaults to loopback on port
   9000. Point the existing same-origin `/peerjs/*` proxy at a signalling process.
   The default local configuration continues to use the singleton route.

ECS task protection holds the owner and any forwarding task while an admitted
WebSocket is active. Idle tasks become eligible for scale-in. A task that receives
SIGTERM marks itself draining, retains existing assignments and waits for sockets
to close up to the configured deadline. A deployment with no spare capacity can
wait for protection to clear. Crashes, forced stops, and relay failures can interrupt
media. At capacity one, recovery waits for a replacement. See the
[ECS task protection endpoint](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-scale-in-protection-endpoint.html).

## Verification

- Run the consultation pytest suite against disposable PostgreSQL. It covers
  concurrent assignment, draining, expiry, stale credentials, reauthorization and
  migration round trips.
- Run `npm test` in `services/signalling` to exercise live WebSocket and HTTP
  forwarding through two server instances with a consultation API fixture.
- Run `node --experimental-transform-types --test probes/video-recovery.test.mts`
  in `apps/web` to check fresh admission, transient failures, stale events and
  cancellation.
- Run the demo-platform Terraform mock tests for managed capacity one and two.
  AWS acceptance should run the doctor and patient in different browser sessions,
  terminate the assigned task while a second task is ready, and verify both regain
  two-way media on the same new owner. Repeat with revoked access and with TURN.
