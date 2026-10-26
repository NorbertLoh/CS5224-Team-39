# Project structure refactor

User-requested structural work after RF21. Issues RF22 #305, RF23 #306 and RF24
#307 are assigned to NorbertLoh and In progress. This document describes the target;
actual implementation/check results are recorded in the phase PRs.

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
