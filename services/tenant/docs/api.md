# A08 clinic APIs

Direct routes below have no prefix. Ingress strips `/api/v1/tenant`; set
`SERVICE_ROOT_PATH=/api/v1/tenant` for externally generated URLs/OpenAPI.

| Route | Behavior |
| --- | --- |
| POST `/clinics` | Verified, provisioned subject. C02 slug/name/branding/SGD price only. New clinic returns 201, pending review, commission 0. Assigns creator admin membership through identity HTTP API. |
| GET `/clinics` | Public active, provisioned profiles; `limit=1..100`, signed cursor, ordered name/tenant ID. |
| GET `/clinics/by-slug/{slug}` | Public active, provisioned profile; otherwise concealed 404. |
| GET `/clinics/{tenant_id}` | Current active owning-clinic admin or platform admin; includes commission/review reason. |
| PATCH `/clinics/{tenant_id}` | Same admins. At least one of name, complete branding, complete consultation price. No null fields or status/slug/commission writes. |
| GET `/internal/clinics/{tenant_id}/booking-profile` | Scheduling service only. Active + provisioned clinic returns public profile and trusted price; inactive/unprovisioned returns 409 `clinic_not_active`, missing clinic 404. |

Public profiles omit commission, review reason and internal provisioning fields.
Creation validates lowercase hyphenated slugs (100 chars), nonblank names (200),
branding color, HTTPS logo URLs without credentials (2048), plain-text description
(2000), and nonnegative safe-integer SGD amounts. Unknown input fields are rejected.
Authentication verifies access-token signature/issuer/expiry/token use/client
before querying identity `/me`; roles are current server-controlled memberships.
Unrelated and revoked admins get 404. No permission cache is used.

## Retryable creation

Tenant first commits a pending clinic with its immutable slug and creator ID.
It then calls identity's authenticated PUT `/internal/clinic-creators`, which may
create only the creator's `clinic_admin` membership. Identity serializes this
with its other membership writes and returns the same row on retries. It does
not restore a revoked/demoted membership or accept arbitrary roles.

Tenant marks provisioning complete only after validating identity's acknowledgement.
Failure returns 503 and retains the hidden, non-bookable clinic. Retry POST with
the same subject, slug and payload resumes that row and returns 200. A successful
repeat also returns 200 while the creator still has admin access; a revoked creator
receives 404. Another subject or changed payload returns 409 `slug_taken`. There
is no queue/retry worker: the caller retries the same request.

Migration 0002 is additive and preserves A07 rows on rollback to 0001. Existing
A07 rows have no recorded creator and default to unprovisioned; an operator must
reconcile their real creator membership before marking them provisioned.

## Configuration and running

Follow the [database setup](../README.md), apply `alembic upgrade head`, install
the locked dependencies and local packages. From `services/tenant`, copy
`.env.example` to ignored `.env` and configure:

- `SERVICE_DATABASE_URL`: tenant role/schema, never the identity database role.
- Cognito issuer, reachable JWKS URL, public app client and required scopes.
- `SERVICE_IDENTITY_URL`: directly reachable identity base URL (for example
  `http://127.0.0.1:8001`; identity independently validates forwarded user tokens).
- `SERVICE_CURSOR_SECRET`: random signing key, at least 32 bytes.
- `SERVICE_TENANT_SECRET`: separate random key shared only with identity for
  creator provisioning. Set identity's new setting to the same value.
- `SERVICE_SCHEDULING_SECRET`: separate booking-gate key shared with scheduling;
  do not reuse identity's scheduling access-decision key.
- `SERVICE_CORS_ORIGINS`: explicit browser origins, such as
  `["http://localhost:5173"]`. Service URLs/origins require HTTPS outside local/test.

```powershell
.venv\Scripts\python.exe -m app
```

Defaults to port 8002. Identity must run separately (port 8001) with its migrations
and explicitly provisioned runtime Cognito subject mappings. Creator provisioning
does not use identity's local clinic fixture adapter. Its general staff/membership
APIs still use that adapter until A10's tenant-directory integration.

Scheduling credentials are HS256 JWTs with issuer `telelink-service:scheduling`,
audience `telelink-tenant-booking`, subject `scheduling`, integer `iat`/`exp` and
at most five minutes lifetime. Tenant issues equivalent short-lived credentials
for identity with issuer `telelink-service:tenant`, audience
`telelink-identity-provisioning`, subject `tenant`, and a 60-second lifetime.
User tokens and other service audiences cannot use these internal routes.

`/health/live`, `/health/ready`, `/docs` and `/openapi.json` are available directly.
Readiness checks required local configuration and tenant migration 0002; it does
not promise upstream identity availability. C01 error envelopes and correlation
headers apply; errors and request logs omit credentials and input values.
The public-list cursors expire in 15 minutes and bind to the active/provisioned
filter and name/ID ordering. Tampered/expired cursors return 422.

## Remaining integration

A09 owns approve/reject/suspend and commission changes with auditing. This task
provides no status-edit bypass. A10 owns general staff administration and the
public doctor directory. S02/S03 must enforce this eligibility gate in actual
slot/hold/booking flows; these services are not implemented by A08. No frontend
or shared Compose/routing changes are included.
