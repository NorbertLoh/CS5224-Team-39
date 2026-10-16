# A10 staff membership integration

A10 reuses the identity service's GET/PUT/DELETE membership routes and its current
role checks, per-clinic write lock and last-active-administrator guard. Identity
validates clinic existence through a narrowly scoped, authenticated tenant API.
Membership rows stay in identity; clinic rows stay in tenant.

Clinic lifecycle state does not prevent staff administration: pending, rejected
and suspended clinics still need administrators. Booking eligibility remains a
separate tenant check. No frontend or root Compose changes are included.

## Setup

Run identity on port 8001 and tenant on port 8002 with their migrated databases
and the same Cognito configuration. In identity set `SERVICE_TENANT_URL` to
`http://127.0.0.1:8002` (or the tenant ingress prefix). Configure
`SERVICE_IDENTITY_SECRET` in **both** services with the same random secret of at
least 32 bytes, different from cursor, scheduling and creator-provisioning keys.
Keep it private. Outside local/test, the tenant URL must use HTTPS.
`SERVICE_TENANT_TIMEOUT_SECONDS` defaults to 3 and accepts 1-30 seconds.

Unset `SERVICE_CLINIC_FIXTURE_PATH` for live integration. The local-only fixture
option remains explicit and cannot be combined with a tenant URL; live failures
never fall back to fixtures. Existing `.env` files must add the new settings.
No migrations or frontend configuration changes are needed.

## API behavior

Use the existing identity routes with a Cognito access token:

- GET `/clinics/{tenant_id}/memberships` lists staff, with existing status filters
  and cursor pagination.
- PUT `/clinics/{tenant_id}/memberships/{subject_id}` with
  `{ "roles": ["doctor"] }`, `["clinic_admin"]`, or both assigns/replaces roles
  and reactivates the same row. Subjects must already be provisioned in identity;
  this API does not create Cognito accounts or grant global roles.
- DELETE the same route revokes membership, retaining the row; repeat deletion
  returns 204. Current permissions take effect immediately without caching.

Active owning-clinic administrators and platform administrators may manage staff.
Unrelated/revoked administrators, doctors and patients receive concealed 404s
before any tenant call. The existing write lock, permission recheck and last-admin
409 guard remain in force.

Tenant exposes GET `/internal/clinics/{tenant_id}/membership-profile`, returning
only `{ "tenant_id": "UUID" }` for an existing clinic, regardless of lifecycle
state. It does not call identity, avoiding a circular request during staff
administration. Missing clinics return 404. Only the identity service JWT is
accepted: HS256, issuer `telelink-service:identity`, audience
`telelink-tenant-memberships`, subject `identity`, integer `iat` and `exp`, lifetime
1-300 seconds. Identity issues a fresh 60-second token for each lookup and
forwards the request ID. User, scheduling and creator credentials are rejected.

Identity checks the returned tenant ID. Timeouts, malformed/mismatched responses,
redirects and upstream authentication/server errors return a sanitized 503 before
membership changes. Unknown clinics retain concealed 404s. No cross-request clinic
or membership cache is used. Readiness remains a local database/configuration
check; it does not assert that the tenant service is reachable.

## Verification

Local disposable PostgreSQL 17 verification: **99 identity tests and 106 tenant
tests passed**; Ruff lint and format checks passed. Existing role, signed-token,
cursor, concurrent mutation and last-admin regression checks remain included.
New checks cover live HTTP request credentials/correlation, authorization before
lookup, missing clinics, outages, redirects, malformed/mismatched replies,
all clinic states and the new endpoint's service credential boundaries.

A separate live HTTP walkthrough ran identity and tenant servers with their own
schema credentials, a local test JWKS endpoint and signed RS256 test-user tokens.
It passed real creator provisioning for two clinics, staff list/assignment/role
replacement/revoke/reactivate, cross-clinic and patient/doctor denial, last-admin
protection, missing-clinic denial, staff administration after suspension, and no
membership change when tenant was stopped. This is a real identity/tenant/database
integration check with synthetic authentication; it does not claim an AWS test.
