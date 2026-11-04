# Cleanup verification and review handoff

RF20 / issue #296. Recorded 26 October 2026 (Asia/Singapore).
Status: all five phase PRs merged on 26 October 2026 with explicit user
authorization to defer manual browser acceptance. Issues #292/#294/#295 are
closed; #293/#296 remain open for the unverified manual checks below.

## Review order

| Phase | Task / issue | PR | Result |
| --- | --- | --- | --- |
| Inventory | RF16 / #292 | [#297](https://github.com/NorbertLoh/CS5224-Team-39/pull/297) | Plan, checked consumers, claims and baseline recorded. |
| UI wording | RF17 / #293 | [#298](https://github.com/NorbertLoh/CS5224-Team-39/pull/298) | Three components changed; only rendered strings differ. Manual screen gate open. |
| Obsolete tooling | RF18 / #294 | [#299](https://github.com/NorbertLoh/CS5224-Team-39/pull/299) | Duplicate webhook spike removed after useful checks moved to active billing suite. |
| Documentation | RF19 / #295 | [#300](https://github.com/NorbertLoh/CS5224-Team-39/pull/300) | Duplicate RF10 note consolidated and stale setup/behavior corrected. |
| Verification | RF20 / #296 | This phase's PR | Evidence and manual acceptance checklist recorded here. |

The PRs were reviewed as a stack, retargeted to main and merged in order with merge
commits, preserving their ancestry. All phase checks passed. The final merge is
`f78534e`. The user explicitly authorized merging despite the deferred browser
gate; no browser result is inferred from that authorization. RF17/RF20 issues stay
assigned to NorbertLoh and In progress until their outstanding criteria are met.

## Checks actually run

| Check | Outcome and practical limit |
| --- | --- |
| Frontend baseline and changed-copy ESLint | Passed with zero warnings. |
| Frontend TypeScript `--noEmit` | Passed. |
| Frontend Vite production build | Passed; existing minified chunk above 500 kB warning remains. |
| Billing Ruff lint / format | Passed across the service, 49 Python files formatted. |
| Isolated Python `pip check` | Passed using the billing lockfile and editable billing/common packages. |
| Webhook tests before cleanup | 29 passed, six PostgreSQL-dependent tests skipped locally. |
| Webhook tests after replacement checks | 32 passed, six PostgreSQL-dependent tests skipped locally. |
| Full local billing suite | 47 passed, 268 skipped, 38 subtests passed. No reset database was configured. |
| RF18 PostgreSQL CI | 315 passed, 38 subtests passed; Ruff and dependency checks passed. |
| Markdown references | All 113 retained Markdown files checked, including this report: zero missing local targets; four heading links in changed documents also checked. |
| Removed-path consumers | No active reference to removed X04 handler/doc/workflow or duplicate RF10 doc; historical inventory paths describe removed artifacts. |
| Combined diff / whitespace | Reviewed; `git diff main --check` passed. |

Local npm is unavailable in this execution environment, so the installed ESLint,
TypeScript and Vite CLI files were invoked through Node 24.19.0. These reproduce
the package scripts. GitHub's frontend jobs also passed using the normal npm
workflow for RF16-RF19. Later phase CI results are recorded in their PR checks.
No application source changed after the passing RF17 build.

The full database result above is from the successful
[RF18 billing CI run](https://github.com/NorbertLoh/CS5224-Team-39/actions/runs/40326377254)
at head `fa3109f72d7361ad38b2e2a0506eb50e1f1d6460`, not a local PostgreSQL run.
Both local and CI billing checks retain the existing Starlette TestClient warning.
The carried loopback test uses the real billing HTTP route and SDK verifier with
an explicit receipt-storage spy; it does not claim durable/payment integration.

Compose, runtime dependency locks, backend application code, API/event contracts,
migrations, seed records and infrastructure are unchanged. No Compose command
needed updating. Local Docker is unavailable, so no new Compose startup result is
claimed. No persistent data reset, payment/refund, courier submission, deployment
or certificate-validation change was performed.

## Required manual screen acceptance

Browser inventory returned `Local browser use is disabled in Work settings`.
The existing local app was not rebuilt/restarted by this cleanup. First serve this
branch's frontend through the existing documented
[local Compose workflow](compose-stack.md) or
[configured frontend development setup](../apps/web/README.md). Then open
[the local HTTPS app](https://localhost:8443) for the Compose workflow, or the URL
printed by the configured development server. Do not interpret old-image wording
as a regression in the PR.

Use existing synthetic records/accounts. These checks need no new provider action.

- [ ] Patient: open an existing medicine checkout. Its footer says
      "Your payment status updates here after confirmation." Existing quote,
      pending-payment and payment-status behavior remains available.
- [ ] Clinic admin: open an existing synthetic consultation payment in Payments.
      Refund detail says "Refund unavailable" and explains that no charge was
      made. No refund action is offered; any refund-review caption is accurate.
- [ ] Clinic admin: inspect an existing eligible provider payment. Its normal
      refund controls still follow existing eligibility/confirmation rules.
      Do not submit a refund for this cleanup check.
- [ ] Patient, doctor and clinic admin: confirm appointment browsing, details and
      consultation-entry eligibility remain unchanged; do not start/complete a visit.
- [ ] Platform admin: confirm the existing workspace loads and navigation works.
- [ ] Inspect available loading, empty and error states for leftover test-oriented
      sentences, readable user guidance and no exposed implementation details.

Record checked branch/head, serving method, roles/states visited and results in
the RF17/RF20 PRs before checking off this gate. If no eligible sample exists,
record the missing scenario rather than inventing a successful result or creating
a provider transaction. Manual checks remain unverified as of this report.

## Retained items and follow-ups

Signalling media/TURN checks, provider feasibility probes, shared fixtures,
automated tests/CI, local seed/refund/slot tools and migration history remain.
Their active consumers or unique coverage are documented in the
[inventory](cleanup-inventory.md). No unused application dependency or broad
refactor was justified. Retiring unique signalling coverage or changing bundle
splitting would be separate work; no additional issue/claim was created for it.
