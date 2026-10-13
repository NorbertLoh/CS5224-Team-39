# A05 identity APIs

These APIs implement [C01](../../../contracts/api-conventions.md) and
[C02](../../../contracts/identity-clinic-access.md) using A04 PostgreSQL persistence.
The A03 RS256 verifier is now shared through `telelink_common`, with settings,
logging, correlation, errors and engine construction. Signature, issuer, expiry,
token use, client and configured scopes are
validated before resolving the runtime Cognito `sub`. Token groups and arbitrary
identity/tenant/role headers never grant permissions.

## Routes and behavior

Ingress strips `/api/v1/identity`; direct service routes are:

| Route | Authentication and behavior |
| --- | --- |
| GET `/me` | Cognito access token; persisted identity and active memberships only; unknown runtime sub returns 403 `identity_not_provisioned` |
| GET `/clinics/{tenant_id}/memberships` | Active owning-clinic admin or platform admin; `status=active\|revoked`, `limit=1..100`, cursor pagination |
| PUT `/clinics/{tenant_id}/memberships/{subject_id}` | Same admins; only `{ "roles": ["doctor"] }`; target subject and clinic must exist; 201 creates, 200 replaces roles/reactivates existing membership |
| DELETE `/clinics/{tenant_id}/memberships/{subject_id}` | Same admins; revokes and retains the row; 204 with no body, including repeated/absent-membership revocation |
| POST `/access-decisions` | **Internal only**; scheduling service JWT, server-side action allowlist and trusted scheduling resource context; returns allow/deny with a safe reason |
| PUT `/internal/clinic-creators` | **A08 internal only**; tenant service JWT, body `{ "tenant_id": "UUID", "subject_id": "UUID" }`. Idempotently assigns the creator's clinic-admin membership; cannot accept arbitrary roles or reactivate a revoked/demoted membership. |

A08 creator provisioning uses a separate `SERVICE_TENANT_SECRET` shared with tenant,
at least 32 bytes and distinct from cursor/scheduling secrets. JWT issuer is
`telelink-service:tenant`, audience `telelink-identity-provisioning`, subject
`tenant`, with integer `iat`/`exp` and a maximum five-minute lifetime. Missing or
wrong service credentials are rejected. Tenant owns clinic existence/creator
verification; this narrowly scoped route does not use the local clinic fixture
adapter or read/write tenant tables. General staff APIs now use live tenant validation; see [A10 setup](staff-integration.md).

Unrelated/revoked clinic admins receive concealed 404 responses before clinic
lookup, including on collection/mutation routes. Platform administration does not
grant clinical access. Patients retain access to their own appointment records;
doctors require both assignment and current active doctor membership. Appointment
cancellation is permitted for the owning patient or owning-clinic admin, per C03.
Doctor-only clinical writes and clinic-admin-only medicine readiness are explicit.
Domain state and audit enforcement still belong to the resource-owning services.

Every public membership mutation takes a PostgreSQL transaction advisory lock
derived from the tenant UUID, then rechecks the actor's current permissions. This
serializes additions, role changes and revocations across replicas, including
self-revocation races. Removing/demoting the last active clinic admin returns
409 `last_clinic_admin`. Operator SQL mutations must use the same lock protocol
or occur while API writes are stopped; direct SQL bypasses application policy.
No permission cache is used. All mutations commit before returning success;
unfinished/failed transactions roll back when their session closes.

Lists order by `(created_at, membership_id)` and fetch one extra row to determine
the next page. HS256-signed cursors expire after 15 minutes and bind to the current
subject, tenant, status filter and ordering. Every page rechecks current access;
tampered, expired or mismatched cursors return 422 with `query.cursor` details.
Changing page size is allowed. Cursors are signed, not encrypted; they contain
IDs and ordering positions, never clinical content.

Business errors use C01 envelopes and sanitized validation details. Correlation
headers match `error.request_id`. UTC timestamps have millisecond precision.
Logs contain route templates/status/timing, never request bodies, credentials,
raw resource paths or query strings. The service uses an explicit CORS origin
allowlist; no wildcard or cookie credentials are enabled.

## Run locally

First follow the [database setup](../README.md) and `alembic upgrade head`.
From `services/identity`, export the values shown in `.env.example` or copy them
to an ignored `.env` for the server. Set the actual local Cognito issuer/JWKS/
client, `SERVICE_AUTH_REQUIRED_SCOPES=openid`, a random cursor signing secret,
and configure `SERVICE_TENANT_URL` plus `SERVICE_IDENTITY_SECRET` shared with tenant
for live clinic validation. For explicit local fixture development, use only
`SERVICE_CLINIC_FIXTURE_PATH=../../dev/fixtures/telelink.json` and unset the tenant URL.
Provision subjects using their actual runtime
Cognito sub as documented in the README; fixtures do not auto-provision identities.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ../../packages/python_common
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\python.exe -m app
```

Direct probes: `http://localhost:8001/health/live` and `/health/ready`.
Docs: `/docs`; snapshot: [openapi.json](openapi.json). Set
`SERVICE_ROOT_PATH=/api/v1/identity` only when using an ingress that strips that
prefix. A05 does not change root Compose, frontend routing or the shared proxy.
Production docs are disabled by default; non-local auth requires the configured
AWS Cognito issuer and matching HTTPS JWKS URL. Readiness checks migrated identity
tables and user-auth/cursor configuration; it does not claim downstream clinic
or scheduling connectivity. Missing clinic/service configuration fails closed
with 503 on the affected routes, and an empty action allowlist permits no actions.

## Service authentication and trusted context

Use a separate random secret of at least 32 bytes for `SERVICE_SCHEDULING_SECRET`;
it must differ from `SERVICE_CURSOR_SECRET`. Only identity and scheduling receive
this secret through private configuration/Secrets Manager. It must never appear
in `VITE_*`, frontend bundles, tokens returned to users or committed files.
Transport must use TLS outside local tests. Key rotation invalidates existing
tokens; no grace period is implemented in this prototype.

Scheduling sends `Authorization: Bearer <JWT>` signed with HS256 and claims:

```json
{"iss":"telelink-service:scheduling","aud":"telelink-identity-access","sub":"scheduling","iat":1791882000,"exp":1791882060}
```

`exp`/`iat` must be integers with a positive lifetime at most 300 seconds. Signature,
issuer, audience, subject, issued-at and expiry are verified. Cognito tokens and
service tokens are not interchangeable. Configure space-separated permitted
actions through `SERVICE_SCHEDULING_ACTIONS`, for example
`appointment.read appointment.cancel clinical.read clinical.write medicine.ready`.
Token role/scope claims cannot expand this server-side allowlist.

The C02 body requires `subject_id`, `tenant_id`, `action` and `resource` containing
`appointment_id`, `patient_id`, `doctor_id`. **Only authenticated scheduling can
supply this resource context.** Scheduling must authenticate the original caller
and obtain appointment tenant/participants from its own stored resource, never
forward browser-supplied participant IDs as proof. Other services need an
authenticated scheduling lookup/delegation before requesting these decisions;
they do not get the scheduling signing secret. Ingress must exclude the internal
`/access-decisions` route. Private networking alone is insufficient, and identity
still authenticates every request. Decisions are not bearer credentials; owning
services must recheck current resource context and legal state at mutation time.

## Integration boundaries and verification

The only clinic adapter currently provided uses the agreed F14 synthetic clinic
IDs, explicitly enabled in local/test environments. Production/development/demo
configuration rejects this fixture option. Without a live clinic adapter,
membership operations remain unavailable outside local tests. A08/A10 must
replace this adapter with authenticated tenant lookup, including pending clinics,
and implement creator membership provisioning. No fabricated clinic records or
cross-service database access is used, and no live tenant/scheduling integration
is claimed. A06 applies reusable checks to consuming endpoints.

Run the disposable-database commands in the README for PostgreSQL-backed API,
signed-token and concurrency checks. They cover unrelated users, revoked staff,
platform clinical denial, last-admin removals, duplicate concurrent PUTs, cursor
scope/expiry, malformed input, service action restrictions, errors and CORS.
Actual local Floci PKCE login, JWKS verification and `/me` runtime mapping were
also checked; real AWS login remains W05. The pinned Starlette test client emits
an httpx deprecation warning; tests pass with the repository's existing lockfile.

Regenerate the consumer snapshot after route changes:

```powershell
.venv\Scripts\python.exe -m scripts.export_openapi
```
