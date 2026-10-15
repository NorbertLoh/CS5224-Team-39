# R02 verification — 15 October 2026

The focused suite runs real PostgreSQL 17 using the restricted `clinical_records`
role. API tests use FastAPI HTTP requests and explicit identity, scheduling and
catalogue adapters. They cover doctor/patient scope, unrelated/cross-tenant/admin
concealment, revocation, all non-writing appointment states, context mismatches,
server-owned links/names, quantity/body tampering, frozen issued content, atomic
replacement rollback, concurrent first writes, pagination scope/tampering and read
audits. A simulated audit insert failure verifies that no content is returned.
Persistence checks cover fresh/repeated migration, metadata drift,
downgrade/re-upgrade, unrelated-schema preservation and restricted role permissions.
Adapter checks cover upstream authentication errors, outage, timeout, malformed
responses, wrong resource IDs, catalogue tenant mismatch and pagination cycles.

Live verification also used real local Floci PKCE/JWKS, identity on port 8001,
scheduling on port 8003, records HTTP on port 18005 and PostgreSQL on port 55431.
A synthetic in-progress appointment was inserted as test setup in scheduling's
local database, then all authorization calls used HTTP. Doctor note creation,
own-patient/doctor reads and two committed read audits passed. Clinic/platform
admins received concealed 404; patient writes and missing/forged tokens were
rejected. Changing the scheduling fixture to completed caused the next doctor
write to return 409 while the patient could still read. The fixture and its
clinical/audit rows were removed afterward. No payment/start-consultation workflow
integration is claimed by that test setup.

Fulfilment D01 is not merged at this point. Catalogue pagination/validation is
adapter-tested against C04, and the runtime fails closed if fulfilment is missing
or unavailable. This is not completed real catalogue integration. R03 owns
issuance and transactional outbox publication, so there is no issue endpoint in
R02. Read/write decisions use scheduling's current HTTP response; no distributed
transaction spans scheduling state changes and clinical commits. Browser, AWS,
PDF generation and fulfilment integration remain unverified.

No shared Compose, routing or contract changes are required by this PR. Set up
the service-local role/schema, migrate to `0002`, and configure `.env` as described
in the service README. Never run destructive migration tests against retained data.
