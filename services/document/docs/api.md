# P03 document API

## Endpoints and access

Run the API separately from the P02 worker. Both use the same document schema.

- `GET /api/v1/document/documents`: optional `appointment_id`, `limit` (1-100,
  default 25) and `cursor`. Returns `{items, next_cursor}` ordered by
  `(created_at, document_id)` descending (newest first), including pending/failed metadata.
- `GET /api/v1/document/documents/{document_id}/download`: returns
  `{download_url, expires_at}` for a ready PDF. Pending/failed documents return
  409 `document_not_ready` after authorisation.
- `/health/live` and `/health/ready`: readiness requires JWT/identity/scheduling
  configuration, a cursor secret and document migration `0003`.

The owning patient or assigned doctor with a current active clinic membership
can access documents. Clinic/platform administrators have no implicit clinical
access. Current identity is resolved on every request; the scheduling API
revalidates appointment ownership with the verified user's token. Tenant,
appointment, patient and any stored doctor ID must match the current appointment.
Unrelated or changed context returns concealed 404 before storage/signing.
An unfiltered list contains only the caller's scoped documents; unsupported roles
receive an empty list. Explicit unauthorised appointment filters return 404.

Lists expose metadata and source IDs, without bucket/key/hash, patient names or
clinical text. Before releasing metadata, a transaction commits a list audit and
individual document read audits. Downloads verify the configured private bucket,
object metadata and size, then persist download intent before signing. The audit
records actor/resource/context IDs, request ID, action and time; no URL or clinical
payload. An audit/storage/upstream failure releases no URL. A download audit
records URL issuance intent, not proof that the browser fetched the object.

Cursors are HMAC signed, expire after 15 minutes and bind to the actor, current
roles/memberships and appointment filter. Responses and signed object downloads
request `Cache-Control: no-store`. Download URLs use SigV4, a UUID attachment
filename and PDF content type. Their configured lifetime is 120 seconds by
default (30-300 seconds); URLs remain bearer capabilities until expiry. Already
issued URLs are not revoked by a later membership change. Do not log or persist
them in frontend state beyond the immediate download action.

## Configuration and startup

Install dependencies as described in the service README, then migrate before
starting the API. From `services/document`, export:

```powershell
$env:SERVICE_DATABASE_URL='postgresql+psycopg://document:local-demo-only@localhost:5432/telelink'
$env:SERVICE_IDENTITY_URL='http://127.0.0.1:8001'
$env:SERVICE_SCHEDULING_URL='http://127.0.0.1:8003'
# Match the real local Floci pool/client; issuer, JWKS and client are required together.
$env:SERVICE_AUTH_ISSUER='http://localhost:4566/<pool-id>'
$env:SERVICE_AUTH_JWKS_URL='http://localhost:4566/<pool-id>/.well-known/jwks.json'
$env:SERVICE_AUTH_CLIENT_ID='<public-client-id>'
# Generate an independent random secret of at least 32 bytes.
$env:SERVICE_CURSOR_SECRET='<random-cursor-secret>'
$env:SERVICE_DOCUMENT_BUCKET='telelink-local-documents'
$env:SERVICE_AWS_ENDPOINT_URL='http://localhost:4566'
$env:SERVICE_S3_BROWSER_ENDPOINT_URL='http://localhost:4566'
$env:AWS_ACCESS_KEY_ID='test'
$env:AWS_SECRET_ACCESS_KEY='test'
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8007 --no-access-log
```

`SERVICE_SCHEDULING_URL` points at the direct scheduling root, without the frontend
prefix; identity similarly uses its direct root. `SERVICE_DOWNLOAD_TTL_SECONDS`
can override URL lifetime. Use different cursor and records service secrets.

When the API runs in a container, `SERVICE_AWS_ENDPOINT_URL=http://floci:4566`
can serve internal S3 checks, while `SERVICE_S3_BROWSER_ENDPOINT_URL` must point
to the emulator's published localhost/127.0.0.1 port as seen by the browser.
The signer signs that endpoint directly; never replace a signed URL's hostname.
A container hostname without a browser override fails API startup. These
loopback endpoints support local browsers on the development machine.

On AWS omit both endpoint overrides and static credentials. Use the task role,
actual private bucket and Cognito settings, HTTPS identity/scheduling endpoints,
and the deployed ingress. The role needs `s3:GetBucketPublicAccessBlock` and
`s3:GetObject` on the configured bucket/objects (and `kms:Decrypt` if SSE-KMS is
introduced). The API never uploads or lists bucket contents. Keep all four
bucket public-access blocks enabled and prevent public bucket policies/ACLs.
Restrict debug SDK logging and disable proxy caching for authenticated routes.
U14 owns frontend proxy/routing and document UI integration; no root Compose or
frontend routing changes are part of P03.

## Verification

See the README for the explicit disposable database/reset configuration.
`pytest -q` covers PostgreSQL schema upgrade/downgrade/parity, PDF templates,
worker/replay behaviour and the API. P03 API checks use real PostgreSQL with
explicit identity/scheduling/S3 adapters; they cover patient/assigned-doctor
access, wrong roles/tenants/users, revoked membership, changed appointment
context, pending/failed states, stable pagination/cursor tampering and fail-closed
audit/upstream/storage behaviour. Signing checks use the real boto3 signer and
verify public host, SigV4, lifetime and attachment parameters.

Verified 16 October 2026:

- All 89 document tests passed on isolated PostgreSQL 17 under the restricted
  document role; Ruff lint and format checks passed.
- A live local HTTP check used real Floci PKCE and JWT verification, the identity
  and scheduling APIs, this document API and Floci S3. Patient and assigned doctor
  lists returned the synthetic document; both signed localhost URLs fetched the
  exact stored PDF bytes. Clinic/platform requests returned 404; missing/invalid
  access tokens returned 401; download audits persisted.
- Identity, membership, appointment and ready-PDF inputs for that HTTP check were
  synthetic fixtures in an isolated P03 database. It did not establish a real
  booking/consultation journey or rerun P02 event generation. Retrieval used an
  HTTP client on the browser machine; U14 browser interaction remains pending.

Real AWS unsigned,
expired and tampered URL rejection remains issue #54; accepted Floci 2.2.0
limitations do not establish AWS privacy/expiry enforcement. Receipt/MC metadata
and templates exist, but P02 currently generates prescription PDFs only.
