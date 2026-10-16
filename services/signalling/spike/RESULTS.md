# X01 observed results

Status: **incomplete — real two-network call evidence is still required**.
Issue #56 stays In progress and PR #57 stays draft. The backlog remains unchecked.

## Local verification — 16 October 2026 (Singapore)

Environment: Windows host, Node 24.13.0, Docker Engine 28.4.0 (Linux containers),
Playwright 1.64.1 bundled Chromium, PeerJS 1.5.5, PeerServer (`peer`) 1.0.2,
coturn 4.6.3. Two browser clients ran on one host with fake media devices.

| Check | Observed result | Limit |
| --- | --- | --- |
| `npm test` | 3 passed: credential generation/validation, binding guards, actual HTTP assets/ID/discovery/private-file routes | No public network |
| Default `npm run test:browser` | Local call, playback, media controls, evidence export, Leave/rejoin and missing-TURN validation passed | Real-TURN negative test requires TURN environment variables |
| Actual coturn, UDP listener | All 3 browser tests passed; relay-only selected local relay candidates at both ends, decoded remote video, sent/received audio/video bytes, rejoined successfully | Local Docker/NAT path, fake devices |
| Actual coturn, TCP listener | Same 3 browser tests passed separately using only `turn:…?transport=tcp` | Local Docker/NAT path, fake devices |
| Invalid TURN password, UDP and TCP | No selected pair, no connected ICE path, no received RTP bytes or decoded video after 8 seconds | Not an expired-credential or long-duration test |
| Coturn example configuration | Started with ignored generated config and local test certificate/key; listeners and relay workers initialised | No public certificate or TLS media call verified |
| Harness HTTPS | `/healthz` returned 200 using explicit test CA trust with hostname verification | Local certificate, not public HTTPS/WSS evidence |
| Compose config | `docker compose -f compose.turn.yaml config --quiet` passed | Does not prove firewall/NAT accessibility |
| Dependency install | Pinned npm dependencies installed; npm reported zero vulnerabilities | Point-in-time install report |

The local relay test used an ignored configuration with a random shared secret,
expiring HMAC credentials, a Docker-published listener and small UDP relay range.
Its advertised address was the host's local interface so allocations could route
through Docker NAT. Unlike the public example, this test configuration permits
private relay destinations and disables TLS because the UDP/TCP listener was the
test target. Those local settings are not a public deployment configuration.

Selected candidate statistics, video playback and RTP counters were asserted by
the tests, rather than inferring connectivity from a PeerServer connection or a
remote stream event. A remote stream object can exist even when ICE fails.
Playwright attaches redacted caller evidence to the successful media test's local
test output. No temporary credentials, raw ICE addresses, keys or config files
are committed. Temporary test containers are stopped after verification.

## Remaining completion evidence

No approved public test host, trusted public DNS/certificates or second-network
participant/device has been established in this session. Do not label local
browser/Docker results as two-network success.

Follow the [verification procedure](README.md#required-two-network-verification)
and fill in actual observations below. Capture evidence from both ends. A desktop
on Wi-Fi and a phone with Wi-Fi off using mobile data is one suitable arrangement.

| Required observation | Result |
| --- | --- |
| Date/time, independently routed network types and browsers/OS | Pending |
| At least 30 seconds of two-way human speech and moving video, normal ICE | Pending |
| Selected pair and RTP increments from both clients, normal ICE | Pending |
| Same two-network call with forced TURN relay at both ends | Pending |
| Forced UDP/TCP/TLS transport observations, clearly identifying any untested transport | UDP/TCP local only; public/TLS pending |
| Invalid and expired credential failures on reachable test host | Invalid local only; public/expired pending |
| Real microphone/camera controls, hang-up, rejoin, permission denial and signalling interruption | Automated local controls/rejoin only; manual cases pending |
| Reviewed evidence attachments from both real participants | Pending |

The minimum X01 gate remains the real normal and forced-relay audio/video calls
across two networks, recorded setup/results, and merged PR. Additional transport
and failure cases above must accurately retain any remaining limitations.
