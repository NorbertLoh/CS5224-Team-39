# Identity persistence (A04)

Identity owns application subjects, runtime Cognito subject mappings, global
roles and clinic memberships under the `identity` PostgreSQL schema. This task
implements persistence only; authenticated APIs and access policies follow in
A05/A06/A10. Contract: [C02](../../contracts/identity-clinic-access.md).

Migration setup and focused PostgreSQL verification will be documented here.
