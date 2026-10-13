# Identity service (A04/A05)

A05 adds authenticated self/membership APIs and service-only access decisions.
See [API setup, authentication and integration boundaries](docs/api.md) and the
[OpenAPI snapshot](docs/openapi.json). Implementation is tracked in issue #60.

Identity owns application subjects, runtime Cognito subject mappings, global
roles and clinic memberships under the `identity` PostgreSQL schema. This task
implements persistence and C02 identity APIs. Reusable checks in consuming services
and live clinic integration follow in A06/A10. Contract:
[C02](../../contracts/identity-clinic-access.md).

## Schema decisions

- `identity.subjects`: server-generated UUID `subject_id`, unique opaque
  `cognito_sub`, nonblank `display_name`, and `global_roles`. Empty global roles
  are valid for staff; only unique subsets of `patient`/`platform_admin` are valid.
- `identity.memberships`: UUID `membership_id`, subject foreign key, external
  `tenant_id`, nonempty unique `doctor`/`clinic_admin` roles, `active`/`revoked`
  status, and timezone-aware `created_at`/`updated_at`. One row per subject/tenant.
  Role order does not affect validity. These fixed C02 role sets are constrained
  PostgreSQL text arrays, rather than a user-editable role catalogue.
- Revocation updates status and retains the membership ID, roles and creation
  instant. Reactivation updates the same row. A database trigger preserves
  `created_at` and advances `updated_at` for ORM and direct SQL updates.
  This retains the revoked row; it is not a complete audit of every role change.
- Deleting a subject with memberships is restricted. There is no foreign key
  to tenant-owned clinics and no cross-service table writes. A10 must validate
  clinic existence through the tenant API. A05/A10 must enforce last-active-admin
  concurrency rules and cache invalidation; A05 serializes membership mutations
  per tenant and reads current permissions without caching.
- A tenant/creation/ID index supports C02 membership pagination. Subject lookup
  and subject/tenant lookup use their unique indexes.

Models use [SQLAlchemy PostgreSQL arrays](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#array-types).
Assign a role list or mutate its `MutableList` while retaining the attached ORM
instance. Never trust Cognito groups, request headers or frontend role selection
as persisted permissions.

## Fresh local PostgreSQL setup (PowerShell)

From `services/identity`, with Python 3.10+ and Docker Desktop running:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
docker run --name telelink-a04-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=a04-local-admin -e POSTGRES_DB=telelink -p 127.0.0.1:55408:5432 -d postgres:17
docker exec telelink-a04-postgres pg_isready -U postgres -d telelink
```

Wait for `accepting connections`. Use `docker start telelink-a04-postgres` if the
dedicated container already exists. The following provisioning script is for a
fresh disposable database and deliberately fails if its role/schema exists:

```powershell
Get-Content -Raw scripts/create-local-schema.sql | docker exec -i telelink-a04-postgres psql -v ON_ERROR_STOP=1 -U postgres -d telelink
$env:SERVICE_DATABASE_URL = 'postgresql+psycopg://identity:local-demo-only@127.0.0.1:55408/telelink'
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check
```

Only the identity role runs migrations. Tables and `alembic_version` are in
`identity`; schema provisioning is an explicit administrator step, not part of
application startup. Rerunning `upgrade head` is safe. Migration reflection is
restricted to this service's schema, following the F04 template; connections use
`search_path=public` to keep reflection unambiguous and `timezone=UTC` for reads.
The environment variable is required for migration commands. The A05 HTTP server
also reads an ignored local `.env`; Alembic still requires the exported variable.

No HTTP server or Compose integration is added by A04. For future deployments,
provide an externally managed database URL with verified TLS, separate migration
and runtime grants, and controlled migration execution before accepting traffic.
Do not reuse demo credentials. Percent-encode URL credentials and keep them out
of Git. See the [F04 migration guidance](../template/docs/database.md).

## Runtime Cognito mapping

The fixed `synthetic-subject-*` values in F14/C02 are examples, not runtime login
identities. An operator provisions each subject with the actual `sub` obtained
from the configured Cognito user pool (for Floci, use its user attributes), along
with explicitly approved application roles. This schema assumes one configured
Cognito issuer; moving pools requires deliberate mapping migration. It does not
auto-create identities from a login or copy token groups into role columns.

An operator-controlled Python session can provision a mapping:

```python
from sqlalchemy.orm import Session
from app.database import create_database_engine, find_subject
from app.models import Subject

engine = create_database_engine()
try:
    with Session(engine) as session, session.begin():
        session.add(
            Subject(
                cognito_sub="REPLACE_WITH_ACTUAL_RUNTIME_SUB",
                display_name="Synthetic patient",
                global_roles=["patient"],
            )
        )
    with Session(engine) as session:
        subject = find_subject(session, "REPLACE_WITH_ACTUAL_RUNTIME_SUB")
        subject_id = subject.subject_id
finally:
    engine.dispose()
```

A05 authenticates the token with the A03 verifier first, then passes its verified
`sub` to `find_subject`. Unknown `sub` returns `None`; the API translates this to C02's
`403 identity_not_provisioned`. Lookup is case-sensitive and treats `sub` as
opaque. Global platform-admin provisioning stays operator-controlled.

## Focused verification

**Use a disposable database only.** The tests commit synthetic data, downgrade
both identity tables, then re-upgrade. Existing identity data is deleted by the
downgrade; the extra reset opt-in prevents accidental execution.

```powershell
$env:TEST_DATABASE_URL = $env:SERVICE_DATABASE_URL
$env:IDENTITY_TEST_ALLOW_RESET = '1'
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pip check
Remove-Item Env:TEST_DATABASE_URL
Remove-Item Env:IDENTITY_TEST_ALLOW_RESET
docker stop telelink-a04-postgres
```

Without `TEST_DATABASE_URL`, PostgreSQL tests are explicitly skipped. The focused
CI workflow provisions a fresh PostgreSQL 17 instance and runs the complete suite.
Tests verify repeat upgrades, metadata parity, runtime mapping, multi-clinic
roles, revocation/reactivation, timestamps, invalid role/status/null rejection,
uniqueness, subject referential integrity, transaction rollback, and downgrade/
re-upgrade. A05 additionally tests signed user/service tokens, clinic access,
pagination, safe errors and concurrent membership mutations. Local verification
also passed with an actual Floci PKCE token, live JWKS retrieval and a provisioned
runtime `sub`. Tenant/scheduling service integration remains future work.
