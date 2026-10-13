# Tenant persistence (A07)

Tenant owns clinic data in the `tenant` PostgreSQL schema, following
[C02](../../contracts/identity-clinic-access.md). A07 adds the clinic model,
service-local migrations and focused persistence checks.

Clinic APIs and booking admission follow in A08; review actions and audit events
follow in A09; identity membership provisioning follows in A08/A10.
