# R04: real clinical records frontend

## Behavior

The doctor opens the booked workspace at
`/doctor/consultation?appointment_id=<id>`. Current clinical autosave, reload,
previous-visit history and consultation controls are documented in the
[clinical UI guide](../apps/web/src/features/records/README.md).
The workspace rechecks appointment detail, loads note/prescription history and
retrieves the owning clinic's active catalogue. The selected catalogue
ID, positive integer quantity and instructions are the only prescription item
inputs sent to records. Names, ownership links, item IDs and timestamps come from
the server. Autosave uses PUT for notes, POST for a new draft and PATCH for an
existing draft; issuance is an explicit POST. Document generation runs separately
through the document worker; issuance does not synchronously produce a PDF.

Saved notes/drafts reload from the API. Notes remain editable during an in-progress
appointment after its prescription is issued. Issued/voided prescriptions are
read-only. Completed appointments can be read but not written. Appointment status
is refreshed every ten seconds; the backend rechecks authorization/state on every
operation. No UI action fabricates an appointment transition.

The patient dashboard loads its real prescription list with cursor pagination.
Expanding a prescription makes a fresh, audited detail request. Summaries use
server clinic IDs, dates, statuses and item counts. Errors hide stale clinical
responses; list/detail loading, empty and retry states are explicit. Frontend
subject filters are defense in depth; records remains the authorization boundary.

Clinical queries and mutations are scoped to the current session and discarded
when inactive. Forms are scoped to the booked appointment; navigation/reload warns
before discarding unsaved changes, and writes remain serialized per form. No clinical
payload is stored in localStorage/sessionStorage. After a failed write, the
workspace disables further writes until Reload records checks the server outcome.
Writes are never automatically retried; a timed-out POST/issue may have committed.

## Local setup

Use the existing service READMEs to provision/migrate identity, tenant, scheduling,
clinical_records and fulfilment and configure the same Floci Cognito issuer/client.
Run each service separately. Default direct ports are identity 8001, tenant 8002,
scheduling 8003, records 8005 and fulfilment 8006. Apply each service's current
Alembic head; RF12's pricing changes require at least clinical-records 0006 and
fulfilment 0007. Catalogue access requires an active doctor membership in the owning clinic.
Create catalogue entries through D01's authorised clinic-admin PUT API. An empty
catalogue disables prescription saves; it never enables free-text fallback.

Configure records with `SERVICE_SCHEDULING_URL=http://127.0.0.1:8003` and
`SERVICE_FULFILMENT_URL=http://127.0.0.1:8006`. Both direct upstream services use
unprefixed paths. Its identity URL points to the same identity service as the UI.
The records `.env.example` now matches D01's 8006 port.

In `apps/web/.env`, keep the existing Cognito/local API settings and add:

```dotenv
RECORDS_API_TARGET=http://127.0.0.1:8005
FULFILMENT_API_TARGET=http://127.0.0.1:8006
```

Restart Vite after configuration changes. From `apps/web`, run `npm ci` and
`npm run dev`. Records routes already contain `/api/v1/clinical-records`, so
Vite preserves that prefix; fulfilment forwarding removes `/api/v1/fulfilment`
to reach its unprefixed routes. Internal records/fulfilment paths, including
percent-encoded internal segments, return 404 at the frontend proxy. AWS mode
uses the configured HTTPS gateway via the existing API base selection; deployment
must supply equivalent routing and exclude internal ingress. No Compose or
API/event contracts changed.

## Verification

Run frontend checks from `apps/web`:

```powershell
npm run lint
npm run typecheck
npm run build
```

`dev/check_records_frontend.py` exercises the actual TypeScript adapters through
Vite against real running local services. Run from the repository root using the
identity virtualenv, with its existing `.env` and synthetic Floci demo accounts.
Set `R04_RECORDS_DATABASE_URL` and `R04_SCHEDULING_DATABASE_URL` to those services'
localhost databases, or provide them in each service's `.env`. Optional localhost
HTTP overrides are `R04_IDENTITY_URL`, `R04_TENANT_URL`, `R04_FULFILMENT_URL` and
`R04_WEB_URL`; defaults are ports 8001, 8002, 8006 and 5173.

```powershell
services/identity/.venv/Scripts/python.exe dev/check_records_frontend.py
```

RF04 removed the frontend test harness; `npm test` is not an available frontend
script. The optional adapter helper below is mutating and must only run against
the explicitly configured local synthetic stack.

This check creates a new synthetic clinic, doctor membership and real catalogue
entry. It inserts one disposable in-progress scheduling appointment as test setup
to isolate its adapter verification from consultation/payment. All records operations
then use the real HTTP services and owning-service authorization. It deletes only
its own clinical rows, pending issuance event, appointment and slot; deactivates
its medicine, revokes its membership/tokens and suspends its synthetic clinic.
Run without a concurrent records outbox publisher so its synthetic event is not
published before cleanup. It never resets a schema or changes an existing clinic.

### Historical R04 evidence (16 October 2026)

At implementation time, 74 frontend tests, ESLint, TypeScript/production build,
Python probe Ruff lint/format and diff checks passed. Real Floci PKCE/JWKS, identity, tenant, scheduling,
fulfilment, clinical-records, PostgreSQL and Vite checks passed. The real adapters
verified durable note/draft saves and reload, trusted catalogue names, draft update,
repeat issuance identity, issued-content locking, patient list/detail access,
patient write denial, clinic/platform clinical-read denial, signed-out failure,
completed-state write rejection and persisted clinical read audits. Synthetic
cleanup completed. Browser form interaction, AWS, actual payment/consultation
admission, private PDFs and dispensing/order integration remain unverified.
Those limits describe the R04 run. Later booked video and document/prescription
journeys are recorded in [V04](V04-booked-video.md), [I02](I02-local-journey.md) and
[document frontend verification](document-frontend.md). Their evidence is separate;
this cleanup does not establish new runtime integration or AWS behavior.
