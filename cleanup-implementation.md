# Phased project cleanup implementation

Status: implementation in progress. RF16 inventory prepared; later phase gates remain open.
Scope and decisions: [cleanup plan](cleanup-plan.md).
Shared backlog: [implementation-plan.md](implementation-plan.md).

Execute phases in order. Each phase depends on the preceding completion gate.
Record actual evidence and blockers below; never infer completion from this plan.
Effort estimates are planning estimates, excluding external access/review waits.

## Phase 1 - Ownership and inventory

Prerequisites: current repository instructions and access to GitHub assignment/status.
Estimated effort: S (1-3 hours).

- [x] Search open and closed issues/PRs for cleanup scope and the proposed task ID.
- [x] Reuse an appropriate open issue or select the next unused refinement ID;
      add its scope, completion criteria, dependencies and estimate to the shared
      backlog, linking these two cleanup documents. Do not reopen completed RF04.
- [x] Create/reuse the issue and verify assignment to the requesting teammate and
      In progress status. Resolve overlapping claims/active PRs before editing code.
- [x] Confirm dependencies and coordinate shared configuration/workflow changes.
- [x] Create a purpose-based phase branch such as `chore/RF16-cleanup-inventory` and open a linked draft PR with the
      task ID in the title and `Closes #<issue-number>` in the description.
- [x] Inventory UI wording, tooling, unused code/dependencies, docs and assets.
- [x] Record each candidate in the PR using the inventory format below.
- [x] Capture applicable baseline checks and distinguish existing failures.

Inventory format:

| Candidate | Keep/replace/consolidate/delete | Reason | Consumers checked | Replacement or coverage | Verification |
| --- | --- | --- | --- | --- | --- |
| See [checked inventory](docs/cleanup-inventory.md) | Recorded | Consumer evidence and decisions | In inventory | In inventory | Baseline recorded |

Start with the UI locations in the cleanup plan; old signalling/webhook/delivery
spikes and their workflows; CI-referenced fixtures; task-specific docs and assets.
These are investigation candidates, not preapproved deletions.

Gate: claim and draft PR exist; every proposed deletion has a documented rationale,
checked consumers and replacement coverage where needed. Uncertain artifacts stay.

Evidence: frontend lint/typecheck/build passed; see docs/cleanup-inventory.md. Issue #292 assigned to NorbertLoh and marked In progress. Phase PR is published with this inventory. Browser/Compose/database acceptance remains pending for later phases.

## Phase 2 - UI copy cleanup

Prerequisite: Phase 1 gate. Estimated effort: S (1-3 hours).

- [x] Apply the exact checkout/refund wording decisions in the cleanup plan.
- [x] Review all four role workspaces and loading/empty/error/success states for
      additional developer-facing instructions; replace with concise user guidance.
- [x] Check backend error mappings so old wording is not reintroduced by a response.
- [x] Preserve internal payment markers, error codes, queries and refund guards.
- [x] Leave stored sample records and seed labels unchanged.
- [x] From `apps/web`, run `npm run lint`, `npm run typecheck` and `npm run build`.
- [ ] Inspect affected screens using existing local accounts/data, including a
      synthetic-payment state with no refund action and normal refund eligibility.

Gate: checks pass, UI language is accurate, and payment behavior is unchanged.
Do not add a frontend test framework that RF04 removed for this copy change.

Evidence: only rendered strings changed in three components; frontend lint/typecheck/build passed. API errors expose codes rather than server messages; refund mapping remains local. Browser automation disabled in Work settings, so screen acceptance remains open. Issue #293; stacked on RF16 PR #297.

## Phase 3 - Obsolete artifacts and focused refactoring

Prerequisite: Phase 2 gate. Estimated effort: M (half a day), revisited after inventory.

- [x] Recheck runtime/configuration/CI/documentation consumers before each deletion.
- [x] Remove confirmed superseded spikes and obsolete fixtures/scripts, preserving
      unique useful verification capability in the active workflow first.
- [x] Update/remove associated dedicated workflows and repair retained commands.
- [x] Remove demonstrated unused components, imports and package dependencies;
      update lockfiles through the owning package manager.
- [x] Simplify directly affected duplication/responsibilities without broad rewrites.
- [x] Retain useful local setup, seed/reset, refund and slot tools, active tests,
      CI, migration history and consultation-window controls.
- [x] Run existing Ruff/tests for changed Python services/shared utilities using
      the applicable service CI commands; run signalling checks if affected.
- [x] Confirm no frontend code/dependencies changed after RF17 checks.
- [ ] Validate affected Compose configuration with the documented profiles/env
      and reproduce changed CI commands locally where supported.
- [x] Confirm no retained import, workflow, package command or setup path points
      at deleted artifacts. Record remaining uncertain items as follow-ups.

Gate: each removal has evidence, relevant checks pass and active workflows remain
usable. New behavior/API/schema changes require separate follow-up work.

Evidence: retired only the isolated billing webhook spike/workflow/lockfile and consolidated its doc; carried unique raw UTF-8, rotation and actual HTTP checks into the active suite. Billing Ruff lint/format and pip check passed. Webhook tests: 32 passed, 6 PostgreSQL checks skipped. Full billing suite: 47 passed, 268 skipped, 38 subtests passed. No disposable PostgreSQL/Docker available; Compose unchanged. Browser gate from RF17 remains open. No speculative application refactor or dependency removal justified. Issue #294.

## Phase 4 - Documentation consolidation

Prerequisite: Phase 3 gate. Estimated effort: M (half a day).

- [x] Assign each retained setup/operations topic one current owning guide.
- [x] Move unique current instructions and verification limitations into that guide.
- [x] Preserve compact evidence summaries and issue/PR references before removing
      redundant task narratives; do not turn local evidence into AWS claims.
- [x] Correct stale status text in root/architecture/service documentation.
- [x] Remove unused documentation images and sample PDFs only after purpose checks.
- [x] Repair inbound links, anchors, commands and CI references for removed paths.
- [x] Keep root navigation concise and preserve backlog IDs, dependencies and
      completion history. Keep cleanup status as planned/in progress until verified.
- [x] Check local Markdown links and referenced script/configuration paths;
      inspect rewritten commands against the current implementation.

Gate: retained guides cover active setup and verification, links resolve, unique
evidence survives and no archive or redundant replacement document is introduced.

Evidence: consolidated RF10 behavior/API/cursor semantics and dated evidence into scheduling-frontend.md, removed the duplicate note and repaired inbound links. Corrected stale architecture, booking/billing, clinical autosave, removed npm test/preview instructions and migration guidance. Added root guide navigation. Checked all 112 tracked Markdown files: zero missing local file links. No documentation assets removed without demonstrated redundancy. git diff --check passed. Issue #295.

## Phase 5 - Final verification and merge completion

Prerequisite: Phase 4 gate. Estimated effort: M (half a day).

- [ ] Run final frontend lint/typecheck/build; run affected service/shared checks
      when subsequent edits require rerunning them. Avoid unrelated test expansion.
- [ ] Confirm affected Compose and CI commands reference retained paths.
- [ ] Smoke-check patient, doctor, clinic-admin and platform-admin workspaces using
      existing local services/accounts; check loading, empty and error states.
- [ ] Verify affected checkout/refund UI, synthetic-payment refund denial, booking
      and consultation entry without submitting new provider transactions.
- [ ] Review rendered UI and targeted keyword results for leftover test-only copy;
      legitimate test terminology in source/developer docs does not fail acceptance.
- [ ] Review the final diff for unintended behavior changes, data changes,
      migration removals, unsupported deletions and broken links.
- [ ] Update PR verification/setup notes with actual commands, outcomes, baseline
      failures and unverified scenarios; ensure required CI checks pass.
- [ ] Keep issue In progress while PR review/merge or required verification remains.
- [ ] After merge and satisfaction of completion criteria, close the issue and
      check off its shared backlog task with the merge/verification references.

Gate: all cleanup acceptance criteria are met and recorded. No completion claim
is made merely because local edits or documentation are finished.

Evidence: not run. Blockers: not assessed. Merge reference: pending.
