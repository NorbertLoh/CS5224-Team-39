# A08/A09 clinic APIs

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
| GET `/admin/clinics` | Platform admin only; all admin profiles, optional status filter, limit/cursor; ordered creation time/tenant ID. |
| POST `/clinics/{tenant_id}/review` | Platform admin only; decision approve/reject/suspend, with required plain-text reason for reject/suspend. Returns admin profile. |
| PUT `/clinics/{tenant_id}/commission` | Platform admin only; strict integer commission_bps from 0 to 10000. Returns admin profile. |

Public profiles omit commission, review reason and internal provisioning fields.
Creation validates lowercase hyphenated slugs (100 chars), nonblank names (200),
branding color, HTTPS logo URLs without credentials (2048), plain-text description
(2000), and nonnegative safe-integer SGD amounts. Unknown input fields are rejected.
Authentication verifies access-token signature/issuer/expiry/token use/client
before querying identity `/me`; roles are current server-controlled memberships.
Unrelated and revoked admins get 404. No permission cache is used.

## Platform review and commission (A09)

Platform permissions come from current identity records, not Cognito groups or
clinic-admin membership. Other roles receive 403 on these platform routes.

Review transitions follow C02: pending review can be approved or rejected;
rejected/suspended clinics can be approved; active clinics can be suspended.
Other transitions return 409 `invalid_clinic_transition`. Approvals accept no
reason; rejection/suspension requires a nonblank plain-text reason up to 2000
characters. Approval clears the current review reason while keeping past reasons
in the audit trail. Approval does not bypass unfinished creator provisioning.

Each review/commission change locks the clinic row and writes an audit event in
the same PostgreSQL transaction. An audit failure rolls back the clinic change.
Concurrent identical requests produce one change/event. A review decision matching
the current status returns the unchanged profile, even if another reason is
supplied. Setting the same commission is also a no-op, preserving the timestamp.
Commission changes affect the current rate; billing must snapshot it at checkout
and keep historical payment amounts unchanged.

Audit events store actor subject UUID, tenant UUID, action, previous/new values,
reason and UTC timestamp in `tenant.audit_events`. They are service-local records
with no EventBridge routing/publication in this task. There is no audit-edit API;
normal SQL UPDATE/DELETE is rejected. Migration downgrade deliberately removes
this table, so the documented test commands require a disposable database.

The admin list includes pending/unprovisioned clinics for review. Its signed
cursors expire after 15 minutes and bind to the actor, status filter and creation/
ID ordering; public-list cursors cannot be reused here. Each page checks current
platform permissions. No additional secrets or configuration are required for A09.

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
Readiness checks required local configuration and tenant migration 0003; it does
not promise upstream identity availability. C01 error envelopes and correlation
headers apply; errors and request logs omit credentials and input values.
The public-list cursors expire in 15 minutes and bind to the active/provisioned
filter and name/ID ordering. Tampered/expired cursors return 422.

## Remaining integration

A09 review and commission APIs are implemented. A10 owns general staff administration and the
public doctor directory. S02/S03 must enforce this eligibility gate in actual
slot/hold/booking flows; these services are not implemented by A08. No frontend
or shared Compose/routing changes are included.

## A10 staff membership integration

GET `/internal/clinics/{tenant_id}/membership-profile` is restricted to the identity
service and returns only the clinic ID, including pending, rejected and suspended
clinics. Configure a separate `SERVICE_IDENTITY_SECRET` shared only with identity.
User tokens and other service credentials cannot use this endpoint. Membership
roles, listing and writes remain identity-owned; see the
[setup, credentials and verification](../../identity/docs/staff-integration.md).

## Managed clinic logo uploads (U02)

Configure `SERVICE_LOGO_BUCKET`, `SERVICE_LOGO_PUBLIC_BASE_URL` and optional
`SERVICE_LOGO_REGION`. Use a separate unversioned branding bucket; local emulator
configuration is `SERVICE_LOGO_S3_ENDPOINT=http://localhost:4566`. AWS uses task-role
credentials; custom emulator endpoints are rejected outside local/test.

| Route | Behavior |
| --- | --- |
| PUT `/clinics/{tenant_id}/logo` | Raw PNG/JPEG/WebP bytes, maximum 2 MB and 4 megapixels; decode, resize to at most 512px, normalize PNG and overwrite the clinic's single managed key. Returns updated admin profile. |
| DELETE `/clinics/{tenant_id}/logo` | Delete the managed object and clear the logo URL; repeat removal is safe. Returns updated admin profile. |
| GET `/clinics/{tenant_id}/logo` | Authenticated stored-image preview, PNG response with no-store. Missing clinic/logo returns 404. |

All three require current owning-clinic admin or platform-admin access. Keys are
server-owned `clinic-logos/<tenant_id>/logo.png`. Versioned/suspended-versioning
buckets are rejected to avoid retaining old images. Storage errors return safe
503 responses. Profile PATCH cannot change logo references when managed storage
is enabled. Configure CloudFront OAC and disable caching for logo keys before
cloud use; the editor preview reads through tenant so local buckets remain private.

See [upload setup and verification](../../../apps/web/src/features/clinic-profile/README.md).
