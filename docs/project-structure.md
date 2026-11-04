# Project structure refactor

User-requested structural work after RF21, completed and merged on 26 October 2026.
RF22 #305, RF23 #306 and RF24 #307 are closed after their respective PRs merged.
This document describes the implemented layout; detailed evidence is in the PRs.

| Phase | Merged PR / commit | Final checks |
| --- | --- | --- |
| Backend HTTP boundaries | [#308](https://github.com/NorbertLoh/CS5224-Team-39/pull/308), `b952d72` | 17 passed |
| Backend workflow packages | [#309](https://github.com/NorbertLoh/CS5224-Team-39/pull/309), `746a517` | 18 passed |
| Frontend feature structure | [#310](https://github.com/NorbertLoh/CS5224-Team-39/pull/310), `5ebcfb4` | Eight passed |

Merge approval does not establish browser verification. Manual UI checks remain
in #293/#296; the running application was not rebuilt or deployed by these merges.

## Backend boundaries

Each service remains independently deployable and owns its database, migrations,
models, schemas and transactions. Shared technical foundations stay in
`packages/python_common`; no shared business model or generic service framework.

Organize substantial Python services around these responsibilities:

```text
app/
  main.py, __main__.py, settings.py
  database.py, models.py, schemas.py
  api/             HTTP routers and request dependencies
  services/        reusable business operations and workflow helpers
  integrations/    owning-service HTTP, provider and storage adapters
  workers/         background orchestration
```

Use only packages that have real responsibilities in that service. Keep small
services small. Root worker modules may remain thin CLI entrypoints where an
existing documented `python -m app.<worker>` command needs preserving. Do not
leave duplicate implementations or forwarding modules solely for internal imports.

Remove dependencies on route modules for DB/auth aliases, lookup/audit/locking
helpers and delivery operations. Keep authorization, idempotency, locking and
commit order unchanged. Split large mixed API modules into resource-specific
routers rather than moving the same monolith under another name.

## Frontend boundaries

Keep feature ownership under `apps/web/src/features`, with focused API, types,
hooks, components and page/workspace groups where a feature is large enough to
benefit. Small features do not need empty folders or one-file layers.

Separate fulfilment API types/transport from order, quotation, delivery and payment
operations. Authentication token access belongs to auth, not the clinic-directory
feature. Keep navigation composition focused on route-to-page mapping and use
feature entry points rather than importing every internal component.

Preserve existing URLs, query keys, cancellation/polling, autosave timing,
session behavior, UI wording and visual layout. No new frontend test framework.

## Verification gates

- Capture and compare complete OpenAPI output for the nine HTTP service apps,
  including path/operation IDs, models, validation and security declarations.
- Update all source, test, monkeypatch, worker, script, Docker and documentation
  import consumers. No stale old-module imports or broken local links.
- Run existing service/shared checks locally, recording skips; require existing
  PostgreSQL/Redis/PDF/SES CI for backend phases.
- Compare preserved CLI entrypoints and application startup/import behavior.
- Run frontend lint/typecheck/build and focused adapter checks where applicable.
  Browser verification remains unavailable unless Work browser settings change;
  do not claim visual/runtime results from a successful build.
- No migration, configuration, provider transaction, data reset or deployment.

## RF22 implementation evidence

Eight substantial HTTP services now have explicit `app/api` packages and request
dependencies. Identity sessions/access decisions are separate from memberships;
clinical notes are separate from prescription endpoints. Reusable identity and
clinic lookup/locking helpers live in `app/services`. Clinical record audit/item
operations take explicit actor/token/request metadata rather than a FastAPI Request.
Distinct clinic-admin versus pickup-admin permission dependencies remain distinct.

OpenAPI for all nine HTTP apps (including the unchanged template) matches the
captured pre-refactor contract exactly: 106 paths, operation IDs, schemas and
validation/security declarations unchanged. Local suites for all eight changed
services passed with the same database-dependent skips as before. Ruff passed.
The architecture check in `tests/architecture` prevents operations, integrations
and workers from depending on HTTP router modules; backend CI runs it.
Full database CI results are recorded in the phase PR before review completion.

## RF23 workflow organization

The next phase separates service operations, HTTP/provider/storage integrations
and background workers. In particular, delivery submission and refund processing
must be reusable without importing API routers. Document rendering gets its own
package. Existing worker CLI module names remain thin entrypoints, while internal
imports and tests use the actual worker/operation modules. Implementation and
verification evidence follows in the phase PR.

RF23 implementation now groups operations, integrations and workers across nine
services, with document rendering separate from storage/download orchestration.
Delivery submission/status transitions, refund processing, price snapshots and
order helpers no longer live in HTTP modules. Tenant provisioning receives its
client/settings/request metadata explicitly instead of a Request object.
Stable root worker modules contain only CLI delegation/error handling; internal
imports use the implementation packages. External notification/replay/seed-render
probes were updated alongside the moves.

All nine OpenAPI snapshots still match exactly. Existing local suites for the
nine changed services passed with their database-dependent skips; the import
boundary guard passes. CLI and full database CI results are recorded in the PR.

## RF24 frontend organization

Large fulfilment and clinical-record features are being organized by workflow,
with API transport/types separate from endpoint operations. Video media, hooks,
room orchestration and controls get explicit homes. Clinic and patient page
composition is separated from reusable navigation/components. Authentication token
and identity lookup move out of the clinic-directory API. Smaller cohesive feature
folders remain small rather than gaining empty layers.

Public feature entry points keep navigation from knowing internal file layouts.
Import rewrites include existing developer adapter probes and documentation.
No URLs, cache scopes, autosave timings, styling or backend contracts change.

RF24 implementation relocates 72 modules into workflow groups, splits records and
fulfilment APIs into focused transport/types/endpoint modules, extracts generic auth
token/identity access and separates record validators from wire types. Navigation
uses public feature entry points and a shared workspace frame. Existing internal
imports use the configured alias; all source URLs/probe consumers were updated.

Local verification: ESLint, frontend typecheck and production build passed. Semantic
AST comparisons preserved all 28 original API function bodies, 98 moved component/
hook bodies and all session function bodies; the generic missing-session wording
is now "Sign in to continue." Seven existing cross-tab session checks passed.
Records/scheduling probes were repaired for the current API/session contracts,
typechecked and verified to resolve through Vite before their missing-context guards.
No live probe or browser operation is claimed. The existing bundle-size warning
remains. CI now checks probe types, runner syntax and the existing session checks.
