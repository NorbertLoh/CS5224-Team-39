# Document frontend integration (U14)

U14 connects the existing P03 API to the patient dashboard, patient/doctor
appointment details and the doctor's consultation records workspace. It adds no
document-generation flow or frontend permission bypass.

## Setup

Start identity, scheduling and document APIs with the same Cognito configuration
and service-owned databases. Follow [P03 API setup](../services/document/docs/api.md)
to migrate document storage to `0003`, configure private S3 access, set the cursor
secret and start the API on port 8007. P02's separately running worker prepares
prescription PDFs; U14 cannot create a ready document by itself.

For local development set these server-only Vite targets in `apps/web/.env`:

```dotenv
IDENTITY_API_TARGET=http://127.0.0.1:8001
SCHEDULING_API_TARGET=http://127.0.0.1:8003
DOCUMENT_API_TARGET=http://127.0.0.1:8007
```

The existing records/catalogue/tenant pages also require their own services as
described in [records frontend setup](records-frontend.md). Restart Vite after
configuration changes. `/api/v1/document/*` is forwarded unchanged to P03 because
the document API owns that full prefix. Run the development server for local
proxy checks; no npm preview command is provided. AWS uses `VITE_USE_AWS=true` and deployed
HTTPS `VITE_AWS_API_BASE_URL`; deployed ingress must route `/api/v1/document/*`
to the document service without caching. No AWS routing is provisioned here.

Signed URLs must already point to a browser-reachable host. For local Floci,
configure P03's `SERVICE_S3_BROWSER_ENDPOINT_URL` to its published localhost port.
The UI never rewrites signed hosts and never sends the API bearer token to S3.
HTTPS links are accepted; HTTP is restricted to localhost/127.0.0.1 in local mode.
Credentialed, executable, fragment-bearing or already-expired links are rejected.

## Walkthrough

1. Sign in as a patient and open `/patient`. The Documents section lists the
   caller's authorised documents. Refresh checks for newly prepared PDFs;
   Load more documents follows the P03 cursor.
2. Open an appointment in the patient schedule to see only that appointment's
   documents. An assigned doctor can do the same from their schedule, or select
   the appointment in `/doctor/consultation` to see PDFs beside clinical records.
3. A pending PDF says Preparing PDF. A failed PDF says PDF unavailable with
   clinic-contact guidance. Neither has a download button.
4. Select Download PDF on a ready document. The button waits while P03 checks
   current access and returns a fresh signed URL. A temporary attachment link
   starts the download without opening a popup. The UI reports only that the
   download was requested, since it cannot observe the browser's file save.
5. On a download/network error, try again to obtain a fresh URL. Refresh a changed
   list; sign in again if the session expired. Server-side authorisation remains
   required for every request, including after clinic membership revocation.

The UI does not cache signed URLs. List metadata uses query keys bound to the
current token, identity/memberships, appointment and clinic; it is removed when
unused. Revocation or a context mismatch hides list contents. Already issued
S3 URLs remain valid for their short lifetime, as described in P03.

## Verification

16 October 2026: all 82 frontend tests, lint, typechecking and the production
build passed. Focused adapter/render checks cover bearer/filter/cursor
forwarding, fresh signed URLs, unsafe/expired link rejection, ready/pending/failed
actions, Singapore dates, pagination/empty/loading states, foreign-clinic
concealment and role/token isolation. Full frontend checks are recorded in PR #151.

Live local verification used Floci PKCE and access JWTs, real identity/scheduling/
document HTTP services, a disposable PostgreSQL 17 database and Floci S3. The
production frontend adapter ran through Vite for both patient and doctor. It
listed three synthetic appointment PDFs, rendered ready/pending/failed states,
and retrieved the exact ready PDF through a fresh signed URL. P03 audited the
requests; clinic/platform requests received 404 and missing/invalid tokens 401.

Identity/membership/appointment and stored-PDF inputs were isolated synthetic
fixtures. This does not establish real booking, consultation, payment or P02
event generation. No browser surface was available: browser click/download,
responsive layout and file-save behaviour remain unverified. Real AWS privacy,
expiry and tamper rejection remain issue #54. Floci's accepted private-access
limitations do not establish AWS enforcement.
