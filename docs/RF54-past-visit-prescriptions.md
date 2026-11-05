# Prescriptions in previous visit notes (RF54)

In the doctor consultation workspace, expand **Previous visit notes**, then a
completed visit. Beneath the saved note, **Prescriptions** shows the medications,
quantities and instructions from that visit. Previously issued prescriptions
that were later voided are labelled as no longer valid. Unissued drafts and
never-issued voided drafts are excluded. No prescribing or ordering controls
appear in this history. Missing notes do not prevent prescription readback, and
each resource has independent loading, empty and retry states.

## Access and contract

`GET /api/v1/clinical-records/prescriptions` accepts optional `history_for` only
with an explicit `appointment_id`. It forwards the current visit anchor to
scheduling's existing history authorization. Scheduling requires the current
assigned doctor and restricts earlier visits to the same patient/clinic and
completed visits before the anchor. Clinical records additionally requires an
active doctor membership and a completed historical visit, filters all four
stored context identifiers, and returns only previously issued records.

History pagination remains newest first and binds its signed cursor to the
current anchor as well as the existing identity/appointment scope. Each page
revalidates access. List and record reads are audited before responding; audit
failure prevents clinical content from being returned. Normal prescription lists,
single-record access and all write routes retain their existing policies.

The frontend fetches all pages only when a historical visit is expanded, passes
the history anchor on every page, and validates each returned record's context.
Current clinical drafts and autosave state are independent of history.

## Setup and verification

Deploy clinical-records before web. No migration, new dependency or environment
setting is required. RF54 is stacked on PR #380 to retain the doctor profile
feature already running locally; its feature diff is PR #382. Issue #381 remains
In progress until merge and completion criteria are met.

- **176 clinical-records PostgreSQL tests passed** on a fresh disposable schema
  with the restricted service role; Ruff checks and formatting passed. History
  checks cover another clinic doctor's read, normal-access/write isolation,
  rejected roles/context, scheduling denial, drafts, issued/voided pagination,
  cursor scope and audit failure.
- Frontend lint, typecheck/build and probe typecheck passed. The new CI probe
  verifies read-only medication rendering, status/empty/loading/error states,
  escaping, paginated history parameters and mismatched-visit rejection.
  Existing navigation/auth probes and four video recovery checks passed.
- Local clinical-records/web images rebuilt and restarted healthy on Tailscale.
  Real doctor-authenticated API reads covered seven earlier visits and six
  prescriptions, plus invalid-anchor rejection. Live browser verification
  confirmed an empty-prescription visit and another visit showing its issued
  medications despite having no saved note. No clinical records, appointment
  status or call state was changed.

AWS rollout remains pending. GitHub-hosted CI has previously been blocked by the
owner's account billing lock; the checks above ran locally.
