# B01 Billing Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add isolated billing payment persistence and prove its database invariants.

**Architecture:** One billing-owned payments table, SQLAlchemy model and initial
Alembic revision. Database constraints and a local trigger enforce stored facts;
the shared database helper supplies PostgreSQL/UTC connection settings.

**Tech Stack:** Python 3.10+, SQLAlchemy 2, psycopg 3, Alembic, PostgreSQL 17,
pytest and Ruff.

**Spec:** `docs/superpowers/specs/2026-10-16-b01-billing-schema-design.md`.

Execution: The user requested implementation after reviewing the specification.
Proceed inline on the existing task branch; record progress in ignored
`.local/task-claims/B01-progress.md`.

## Global Constraints

- Scope: issue #137; branch `codex/B01-billing-schema`; draft PR #138.
- Use the `billing` schema and restricted role; no cross-service foreign keys.
- Money is nonnegative SGD bigint, at most `9007199254740991`.
- Commission is `floor(commissionable_minor * commission_bps / 10000)`;
  rate range is 0 through 10000 inclusive; delivery fees are excluded.
- Snapshot/ownership fields are immutable; provider references remain internal.
- Only the disposable B01 database may be reset; require `BILLING_TEST_ALLOW_RESET=1`.
- Keep the issue In progress and B01 unchecked until merged.

## Review Focus

- Large valid commission inputs must not overflow bigint multiplication.
- Null provider accounts share a namespace; absent references allow multiple rows.
- A failed attempt's late success must remain representable beside another success.
- Direct SQL cannot bypass snapshot immutability or timestamp handling.
- Migration/reset paths must preserve unrelated schemas and fail without consent.

## Task 1: Payment schema, migrations and persistence checks

**Files:**
- Create `services/billing/app/{__init__,database,models}.py`.
- Create `services/billing/alembic.ini`, `migrations/env.py`,
  `migrations/script.py.mako`, `migrations/versions/0001_payments.py`.
- Create `services/billing/pyproject.toml`, `requirements.lock.txt`, `.env.example`.
- Create `services/billing/scripts/create-local-schema.sql`, `create-test-sentinel.sql`.
- Create `services/billing/tests/{conftest,test_migrations,test_payments}.py`.

**Interfaces:**
- Consumes `telelink_common.database.create_postgres_engine(url, **kwargs)`.
- Produces `app.models.SERVICE_SCHEMA`, `Base.metadata`, `Payment` and
  `app.database.create_database_engine(url: str | None = None, **kwargs) -> Engine`.
- Alembic consumes `SERVICE_DATABASE_URL`; tests consume `TEST_DATABASE_URL` and
  `BILLING_TEST_ALLOW_RESET=1`.

- [x] Write real PostgreSQL tests for migration upgrade/downgrade, restricted-role
  isolation, both payment purposes, statuses, money/link constraints, unique
  provider namespaces, immutable snapshots and timestamps.
- [x] Run `python -m pytest tests/test_migrations.py -q` against the disposable
  database. Expected RED: initial migration is unavailable.
- [x] Add the package/configuration, shared-helper wrapper, table columns and
  migration matching the spec; provision only the new disposable database.
- [x] Run the full tests. Add constraints, provider indexes and trigger only after
  observing the corresponding failures. Expected GREEN: all database cases pass.
- [x] Verify literal commission cases: `(2000,500,1000)->(2500,200,2300)`,
  `(1,0,3333)->(1,0,1)`, zero/full rates and the safe-integer maximum.
- [x] Verify missing reset consent fails before downgrade, and missing database
  configuration skips persistence checks explicitly.
- [x] Run `python -m ruff check .`, `python -m ruff format --check .`,
  `python -m pip check` and `python -m pytest -q` from `services/billing`.
- [ ] Commit the schema, migration and tests.

## Task 2: Reproducible setup, CI and review

**Files:**
- Create `services/billing/README.md` and `.github/workflows/billing-checks.yml`.
- Update the spec status and this plan's completed steps.

**Interfaces:**
- Consumes Task 1's provisioning scripts, lockfile, environment variables,
  migration command and pytest suite.
- Produces service-local setup instructions and a PostgreSQL-backed CI job.

- [x] Document first-time provisioning, explicit Alembic environment configuration,
  upgrade/check/downgrade behavior, synthetic examples and the separate test DB.
- [x] Add the service-scoped workflow using PostgreSQL 17 and Python 3.10, restricted
  billing credentials, explicit reset consent, Ruff and full pytest.
- [x] Re-run the documented migration cycle and checks, verify unrelated sentinels
  survive, and record observed results without claiming provider integration.
- [ ] Request a fresh whole-branch review against this plan/spec and C01/C03/C04;
  fix actionable findings with a regression test and rerun the relevant suite.
- [ ] Commit/push the implementation and replace PR #138's description with final
  behavior, setup and verification evidence. Preserve `Closes #137`.
- [ ] Inspect GitHub checks; leave any real limitation explicit and keep the issue
  open until merge. Stop only the specifically created B01 test container.
