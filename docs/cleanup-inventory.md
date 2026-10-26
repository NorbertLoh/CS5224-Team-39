# Cleanup inventory and decisions

RF16 / issue #292. Inspection baseline: `a059bb4` on 26 October 2026.
Scope: [cleanup plan](../cleanup-plan.md); [execution checklist](../cleanup-implementation.md).
This is an inspected candidate list, not a claim that subsequent phases are complete.

| Candidate | Decision | Evidence / consumers | Replacement and verification |
| --- | --- | --- | --- |
| Medication checkout test sentence | Replace in RF17 | Rendered by `LiveMedicationCheckout`; no behavior change needed. | Use the plan's neutral confirmation sentence; lint/typecheck/build and screen review. |
| Payment/refund demo headings and messages | Replace in RF17 | `PaymentDetails`, `ConsultationRefund`; mapped `refund_demo_payment` response. | Keep the marker, error code and disabled refund/history guards; explain that no charge was made. |
| `services/billing/spike/` and dedicated workflow | Replace, then delete in RF18 | Only dedicated CI and `docs/stripe-webhook-spike.md` reference the standalone issuer. Billing runtime uses `app/webhooks.py`. | Current billing tests cover signature/header/timestamp/body/size/privacy/rotation failures. Carry UTF-8/reserialization and actual loopback transport coverage into the active tests before removing the isolated harness. Retain a concise historical evidence summary in `WEBHOOKS.md`. |
| `services/signalling/spike/` and CI | Keep | Old two-browser call suite checks bidirectional audio/video, media controls, redacted stats and forced TURN; current packaged browser suite primarily checks data exchange/rejoin. | Unique media/TURN verification remains useful for RF01. No deletion without replacement coverage. |
| Billing `scripts/stripe_spike.py` | Keep | Active billing `tests/test_stripe_spike.py`, documented Connect/fee inspection commands. | Distinct provider-feasibility checks; not replaced solely by application checkout. |
| Fulfilment `scripts/lalamove-spike*.mjs` and CI | Keep | Dedicated provider-boundary tests and reproducible sandbox commands. | Retain operator verification; no courier submission during cleanup. |
| `dev/fixtures/` | Keep | Backend lint CI, identity `tests/test_api.py`, identity fixture-path example and docs. | Active deterministic test/configuration consumers. |
| Seed/reset, `refund_demo.py`, `test_slots.py` and local join flags | Keep | Documented local workflows and safeguard tests. | Preserve flags, seed markers, existing data and migration 0003. |
| Existing service tests, template and common package | Keep | Active CI installs/runs template and shared tests; service ownership remains independent. | Do not remove based on names or apparent scaffolding. |
| Root/feature/service documentation | Consolidate in RF19 | `plan.md` introduction predates implemented services; scheduling guide still advertises removed frontend tests and disconnected billing. | Correct current behavior against actual routes/scripts; keep historical verification labeled historical. |
| X04 webhook setup document | Consolidate/delete with RF18 | Commands launch the superseded isolated handler; backlog and billing README link to it. | Move unique evidence and current commands to billing `WEBHOOKS.md`; update inbound links in same PR. |
| RF09/RF10 notes and design screenshots/PDF samples | Keep unless redundancy is demonstrated | Notes carry cursor/API semantics and live evidence; samples support PDF/sign-in design reference. | Do not delete unique evidence/assets just to shrink the repository. |
| Imports/dependencies/large components | Keep unless demonstrated unused | No proven unused runtime dependency or unsafe large-module responsibility found in this pass. | Avoid speculative refactoring; lint catches unused imports. |
| Generated caches, runtime data and `dist/` | Keep ignored | `.gitignore` already excludes caches/build/runtime state. | No recursive local cleanup or data reset. |

## Baseline evidence

Frontend ESLint, TypeScript `--noEmit` and Vite production build passed using the
installed package CLIs through Node 24.19.0. npm is absent from this execution
environment; direct CLIs reproduce the three package scripts. The existing build
warns about a minified chunk above 500 kB; bundle splitting is outside this cleanup.

Browser inventory reports: `Local browser use is disabled in Work settings`.
Rendered all-role/synthetic-payment checks remain required and unverified.
The local HTTPS app responds, but its local CA is not trusted by the bundled Node
runtime. No certificate validation settings were changed.

The bundled Python initially has none of the billing test dependencies. Docker is
not available on the execution PATH or its standard Windows installation path.
Backend checks require an isolated environment; PostgreSQL integration, Compose
and browser checks must remain explicit pending items unless a later phase can
provide those runtimes. No persistent database or provider operation is authorized
by this inventory.

## Review sequence

RF16 #292 -> RF17 #293 -> RF18 #294 -> RF19 #295 -> RF20 #296.
Each issue is assigned to NorbertLoh with `status: in progress`. All five IDs were
searched across open/closed issues and PRs before creation. Open PR #233 concerns
AWS Terraform and does not overlap the selected changes.

Later phases may prepare independently reviewable draft changes while browser or
runtime acceptance remains pending; this does not satisfy or waive a phase gate.
Merge in order, and keep required checks/issue completion open until verified.
