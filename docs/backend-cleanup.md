# Deeper backend cleanup (RF21)

Issue #302; assigned to NorbertLoh and marked In progress. Based on merged cleanup
stack #297-#301. Status: implementation and local checks complete; PostgreSQL CI
passed on runtime revision `a7074a5`. PR #303 remains unmerged for review.

## Inspected scope and decisions

Inspected the runtime module inventory across all ten Python services (including
the template), shared Python foundations and the signalling service. Compared
pagination implementations, startup/resource lifetime, HTTP boundaries, worker
entry points, fixture consumers and top-level symbol references across source/tests.
The largest runtime modules remain below 300 lines; size alone does not justify splitting.

| Area | Finding and action |
| --- | --- |
| Identity, tenant, scheduling, billing, fulfilment, clinical records, document | Repeated HS256 cursor signing/expiry/required-claim mechanics. Extract only these technical mechanics into `telelink_common.pagination`; keep resource claims, scopes, parsing, errors and queries local. Include the identity doctor-directory cursor. |
| Fulfilment | `DispensingSource` protocol has no consumer in source/tests; remove it and its otherwise-unused Protocol import. Keep the actual HTTP/fixture adapters and their safeguards. |
| Notification | `EmailSender` protocol has no consumer in source/tests; remove it and the unused Protocol import. Keep SES behavior and provider error handling unchanged. |
| Consultation, service HTTP clients and startup | Different timeouts, authentication, endpoint/status rules and close behavior are intentional. Keep these service-local rather than wrapping them in a generic client/factory. |
| Signalling | Admission/parser/shutdown code and active tests remain separate from Python cursor mechanics; no proven unused runtime code identified. Keep unique media/TURN spike checks. |
| Models, migrations, workers, tests and fixtures | Active schema/transaction ownership and verification consumers. No keyword-based deletion or database change. |

No API/event contract, environment variable, cursor issuer/audience/lifetime,
scope binding, response shape or dependency version changes are intended.
Already-issued cursors must remain readable. The tenant admin cursor's nullable
status remains present-but-not-required by JWT's non-null claim rule.
Authorization, tenant filtering and SQL pagination remain in each owning service.

## Verification plan and evidence

- Preserve existing service cursor functions and return types for their callers.
- Check shared JWT behavior: expiry, wrong key/algorithm/issuer/audience, required
  fields and missing configuration; do not move business authorization into shared code.
- Compare old and new encoders/decoders in both directions using equivalent rows,
  roles, scopes and filters, including tampering and nullable admin status.
- Run shared tests and available service tests locally without a persistent data reset.
- Require existing per-service PostgreSQL CI and Ruff checks for the shared change.
- No frontend, provider transaction, Compose startup or deployment needed for this refactor.

### Local results

All ten Python service suites and the shared suite ran in separate processes with
their service import paths, without a reset database. Ruff passed across all ten
services and common code; format checks passed for changed Python files, and
`pip check` passed in the isolated test environment.

| Suite | Passed | Skipped locally |
| --- | ---: | ---: |
| Identity | 17 | 133 |
| Tenant | 6 | 125 |
| Scheduling | 35 | 229 |
| Billing | 47 + 38 subtests | 268 |
| Fulfilment | 96 | 282 |
| Clinical records | 26 | 139 |
| Document | 44 | 61 |
| Notification | 62 | 29 |
| Consultation | 37 | 96 |
| Template | 37 | 1 |
| Common | 110 | 12 |
| Total | 517 + 38 subtests | 1,375 |

The shared suite includes 17 new JWT compatibility/failure checks. An additional
local differential probe loaded original cursor functions from merged baseline
`f78534e` and compared them with the refactor: 12 cursor variants and 201 old/new
behavior comparisons passed. These covered both directions, exact decoded claim
sets, the 900-second lifetime, missing claims, expiry/future issue time, wrong
issuer/audience/scope/order/subject/tenant, malformed IDs, timestamps without a
timezone, both fulfilment value modes and nullable tenant-admin status.
The probe is an ignored local audit tool; permanent regression coverage is in
the shared tests and existing service suites, not a dependency on Git history.

Database/emulator-dependent tests are skipped locally, not claimed passed.
Existing PostgreSQL CI passed for identity, tenant, scheduling/Redis, billing,
fulfilment, clinical records, document/PDF, notification/SES and consultation at
runtime revision `a7074a5`. Backend/common/template, seed safeguards and frontend
jobs also passed. Exact check/run links are in
[PR #303](https://github.com/NorbertLoh/CS5224-Team-39/pull/303/checks).
All 114 Markdown files were checked for local links with no missing targets.
Subsequent documentation-only evidence changes do not change that runtime result;
normal PR checks must also pass on the final head before merge. The
existing Starlette TestClient deprecation warning remains. A full-directory Ruff
format check also flags an existing Python snippet in the common README; changed
Python files themselves pass, and that unrelated snippet was not reformatted.

### Setup impact and remaining acceptance

No new dependencies, environment settings, migrations, API/event shapes or data
changes. Existing editable common-package installs pick up the new module.
Rebuild service images or reinstall the common wheel together with service code;
restart updated APIs so imports use the matching common package. Services retain
their existing entry points and deployment boundaries.

Required manual UI follow-ups from RF17/RF20 stay in issues #293/#296 and are not
established by backend checks. This PR remains unmerged pending review.
