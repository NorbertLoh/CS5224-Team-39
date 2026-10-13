# A06: reusable tenant and role checks

The template's `GET /clinics/{tenant_id}/access` demonstrates the shared
`require_tenant_role('clinic_admin', allow_platform_admin=True)` dependency.
It returns only `subject_id`, `tenant_id` and `allowed: true`; it does not return
clinic records or assert that the clinic exists. Business endpoints must validate
their own resource existence, tenant/participant links, legal state and audit rules.

Configure the A03 Cognito issuer/JWKS/client and `SERVICE_IDENTITY_URL` pointing to
identity's base URL. Direct local example: `http://localhost:8001`. Through an
ingress, include its `/api/v1/identity` prefix. The shared client appends `/me`.
Non-local identity lookup requires HTTPS, and redirects are not followed. The
default lookup timeout is three seconds (`SERVICE_IDENTITY_TIMEOUT_SECONDS`).

The template verifies the user token, forwards that same token to identity, checks
the returned runtime sub matches the verified principal, and validates the response
membership ownership and roles. Identity independently authenticates the token and
loads current persisted permissions. There is no cross-request permission cache.
Only an active clinic-admin membership in the selected clinic, or an explicitly
allowed persisted platform-admin global role, passes. Spoofed identity/role headers,
Cognito group claims, revoked staff and unrelated clinics do not grant access.
Missing lookup configuration/network failure returns 503; invalid upstream data
returns 502; unauthorized clinic access is concealed with 404. Error bodies use C01.

Run identity using its [setup guide](../../identity/README.md), provision the actual
runtime Cognito sub, and create an approved synthetic clinic membership. Run this
service from `services/template` with the same Cognito configuration and the
identity URL, then call `/clinics/<tenant UUID>/access` with the user's access token.
Revoking that membership must deny the next request with the same token. Calls
without a bearer token remain 401 even if identity/role headers are supplied.

Reuse the shared [package](../../../packages/python_common/README.md) directly in
future services. `require_global_role('patient')` checks persisted global roles;
`require_tenant_role('doctor')` checks current clinic membership without granting
platform administrators an implicit doctor/clinical permission. Domain models,
transactions, appointment rules and migrations remain with their owning service.

A06 verification includes shared-client/policy tests, the full existing identity
PostgreSQL suite, template token/logging tests, production/development container
packaging, and actual HTTP between two localhost services with live Floci JWT/JWKS
and a PostgreSQL-backed membership. Live tenant/scheduling business integration
remains future work; the permission probe uses no resource fixtures.
