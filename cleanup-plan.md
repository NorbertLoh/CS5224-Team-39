# Project cleanup plan

Status: planned; no cleanup implementation or runtime verification is recorded here.
Prepared: 26 October 2026.

Execution checklist: [phased implementation](cleanup-implementation.md).
The shared backlog remains [implementation-plan.md](implementation-plan.md), and
[plan.md](plan.md) remains the architecture and scope source.

## Goal and scope

Make the project easier to understand and maintain, remove confirmed obsolete
artifacts, and replace developer/test-oriented UI sentences with useful product
language. Audit the whole repository, but keep refactoring focused on demonstrated
dead code, duplication and directly affected responsibilities.

RF04 already removed frontend test harnesses and synthetic preview routes in
merged PR #259, with completion recorded in #260. Do not repeat that work or
restore those harnesses as part of this cleanup.

This plan includes UI copy, obsolete tooling, unused application code and
dependencies, redundant documentation and unreferenced documentation assets.
It excludes redesign, broad architecture changes, API/event/schema changes,
database resets, migration removal, changes to existing sample records or future
seed labels, deployment and live provider transactions.

## Cleanup decisions

### Application language

Review patient, doctor, clinic-admin and platform-admin workspaces, including
loading, empty, error and success states. Remove implementation commentary and
test instructions from normal screens while retaining useful user guidance.

| Current wording | Replacement |
| --- | --- |
| Stripe test checkout. Your payment status updates here after confirmation. | Your payment status updates here after confirmation. |
| Demo payment | Refund unavailable |
| Demo refund-review example. No money was charged. | No charge was made, so there is nothing to refund. |
| This is a demo/simulated payment explanation in refund UI | No charge was made, so there is nothing to refund. |

Initial locations are `LiveMedicationCheckout`, `PaymentDetails` and
`ConsultationRefund` under `apps/web/src/features/`. Inspect rendered screens
and API error mappings for additional examples. Do not blindly replace words in
identifiers, regular-expression `.test()` calls, medical terms or development docs.

Preserve `demo_payment`, `refund_demo_payment`, provider markers, disabled refund
queries/actions and backend refund eligibility checks. Synthetic records must
remain accurately described; neutral wording must not imply a charge occurred.
Provider test/sandbox settings remain unchanged and documented in developer guides.

### Tooling and code

Classify candidates as **keep**, **replace**, **consolidate** or **delete**.
Deletion requires checked runtime imports, dynamic/configured references,
package scripts, Compose/Docker usage, CI workflows and documentation consumers.
No references alone do not prove an operator-invoked tool is obsolete: check its
documented purpose and whether a current workflow replaces it.

Audit old signalling, Stripe webhook and delivery spikes first. Remove them only
when current implementations cover their purpose and necessary verification.
Preserve or relocate unique useful checks before retiring their old harness.
Update dedicated CI workflows and commands together with any approved removal.

Keep active automated tests, CI, service scaffolding used by checks, local setup,
seed/reset safeguards, useful refund/slot helpers and local consultation controls.
Fixtures referenced by CI are not automatically obsolete. Keep database migration
history, including consultation migration 0003 and existing early-start semantics.

Remove unused components, imports and dependencies only with consumer evidence.
Keep dependency and lockfile edits together. Refactor directly affected duplication
or tangled code into focused functions/files; do not standardize every service,
rename all `Live*` components or introduce a new shared abstraction layer.
Leave uncertain candidates in place and list them as follow-ups.

### Documentation

Keep a clear root entry point linking current setup, architecture, contracts,
service guides and operational instructions. Consolidate current instructions from
task-specific notes into their owning guides, then remove redundant historical
narratives. Do not create an archive directory.

Preserve unique verification evidence, issue/PR links, unfinished work and limits
of local versus deployed AWS verification. Correct stale current-state claims,
including the architecture introduction saying no business workflows exist.
Keep backlog IDs, dependencies and completion history. Remove screenshots/sample
PDFs only after confirming they no longer serve a current design or verification
purpose. Repair all affected links in the same change.

## Delivery and acceptance

Follow [AGENTS.md](AGENTS.md) before implementation: search issues/PRs, establish
the cleanup task ID and requesting teammate's claim, check dependencies, use a
purpose-based task branch and open a linked draft PR early. Coordinate shared
workflow, routing and Compose edits. Do not claim other teammates' work.

Record each deletion's reason, consumers checked and replacement coverage in the
PR. Use the phased checklist for evidence and blockers, not as an assignment source.
Keep the issue In progress until merge and completion criteria are met.

The cleanup is accepted when:

- Normal application screens contain useful product copy rather than test-only
  instructions; synthetic-payment explanations remain truthful.
- Every deletion has evidence, and no active workflow or reference is broken.
- Active tests, CI, setup commands, payment guards and service boundaries remain.
- Current guides cover retained setup/verification commands without redundant notes.
- Frontend lint/typecheck/build and relevant existing backend/signalling checks pass.
- Affected Compose/CI commands and documentation references are validated.
- Local smoke checks cover all four roles and relevant checkout, refunds, booking
  and consultation entry behavior; unverified scenarios are explicitly recorded.

Checks use existing local services and sandboxes. Do not create charges, refunds,
courier orders or reset data simply to verify copy. Existing evidence cannot be
reported as a new successful run. Blocked required checks keep the corresponding
phase open or require an explicitly documented change to acceptance criteria.
