# U02 clinic profile editor and logo upload

Default fixture previews:
`/clinic-admin/clinics/demo-clinic-a/profile` and
`/clinic-admin/clinics/demo-clinic-b/profile`.

## Components

- `ClinicProfileEditor.tsx`: fixture/API lookup, saved/draft profile state and actions.
- `ClinicProfileForm.tsx` and `ProfileField.tsx`: accessible fields and errors.
- `BrandingPreview.tsx`: live visual preview and icon fallback.
- `LogoUpload.tsx`: simple file picker, replacement/removal, status and blob cleanup.
- `logo-api.ts`: authenticated profile/logo API calls and file checks.
- `demo-storage.ts`: clinic-scoped browser saves and persistent local logo previews.
- `profile.ts`: profile validation and exact SGD cents conversion.

## Fixture mode

`VITE_CLINIC_PROFILE_API_ENABLED=false` is the default. Clinic data comes from
U01's public-only agreed fixture projection. Save writes editable profile fields
to localStorage, scoped to the clinic, and restores them after navigation/reload.
Local logo changes save immediately as image data URLs; replacement/removal
overwrites the previous saved preview. Nothing is sent to S3 or published to the
live clinic. Discard restores the last saved fields; it does not undo immediate
logo changes. Confirmation and errors appear beside the Save/Discard controls.
Blocked/full browser storage reports a failure and keeps the unsaved edits.
Clear site storage to restore all original demo fixtures. The editor labels this
mode explicitly; browser-saved values cannot establish permissions for live APIs.

## Live mode

Set `VITE_CLINIC_PROFILE_API_ENABLED=true` and restart/rebuild Vite. Configure
`TENANT_API_TARGET=http://127.0.0.1:8002` for the local proxy (server-only). The
browser still uses `VITE_API_BASE_URL=/api/v1`; production ingress must route the
tenant prefix. Sign in from the home page with a provisioned clinic administrator
or platform administrator, then open:

`/clinic-admin/clinics/<actual-tenant-UUID>/profile`

The fixture slug links also work if those exact fixture tenant IDs have been
provisioned. Live lookup uses tenant's existing authenticated GET endpoint;
profile Save uses PATCH. Server-side identity/clinic-role checks decide access;
fixture IDs and browser state never grant permissions. Failed requests keep
unsaved form edits and show safe feedback. Expired/missing sessions require sign-in.

Choose a PNG, JPEG or WebP logo up to **2 MB and 4 megapixels**. Upload and removal
save **immediately**, independently of profile Save/Discard. The server decodes
and normalizes uploads into PNG thumbnails up to 512 pixels and strips metadata.
The editor previews the stored image through an authenticated tenant read, so
local S3 need not be public or expose browser credentials. Reload keeps live saves.

Names, descriptions, hex colours and SGD fees follow C02/tenant validation.
Slug, lifecycle state and commission remain outside the writable payload. Manual
logo URLs are gone from the UI; the server supplies `branding.logo_url`.

## Tenant/S3 setup

Install tenant's updated `requirements.lock.txt` (boto3 and Pillow added). No
schema migration is required. In tenant set:

```text
SERVICE_LOGO_BUCKET=your-branding-bucket
SERVICE_LOGO_PUBLIC_BASE_URL=https://your-cloudfront-asset-domain
SERVICE_LOGO_REGION=ap-southeast-1
```

Use a **separate unversioned branding bucket**, not the private medical-document
bucket. Tenant's AWS role needs `s3:GetBucketVersioning` on that bucket and
`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `clinic-logos/*`. Use the normal
AWS credential chain/task role; no credentials belong in frontend configuration.
Keep S3 public access blocked and serve public logos through CloudFront OAC.
For `/clinic-logos/*`, use a caching-disabled policy so replacing a stable logo
URL is visible immediately. CloudFront/IAM provisioning remains infrastructure work.

The service stores exactly one key per clinic:
`clinic-logos/<tenant-UUID>/logo.png`. Replacement overwrites that object, so old
files do not accumulate. Remove deletes that key. Enabled **or suspended** bucket
versioning is rejected because it would retain previous images. Object keys are
server-generated; clients cannot delete another clinic's key. Legacy external
logo URLs are never treated as files the project owns or may delete.

For local Floci only, additionally set
`SERVICE_LOGO_S3_ENDPOINT=http://localhost:4566`. The emulator client always uses
dummy credentials. Create `telelink-local-branding` separately without enabling
versioning and keep its public access block enabled. A dummy HTTPS asset base can
be used locally; authenticated preview reads do not depend on that domain.

S3 and PostgreSQL are not a single transaction. If a database commit fails after
an object change, retry the operation: the fixed key makes replacement/removal
converge without accumulating abandoned files. S3 failures leave database logo
metadata unchanged. Generic profile PATCH cannot change the logo reference when
managed storage is enabled; use upload/remove instead.

## Verification

From `apps/web`: `npm test`, `npm run lint`, `npm run build`.
From `services/tenant`: run the existing disposable PostgreSQL suite and Ruff.

Local verification passed **27 frontend tests and 111 tenant tests**, lint,
TypeScript/build, dependency checks and formatting. Coverage includes amount and
URL/field limits, file picker checks, decoded image limits, tenant-role denial,
one-object replacement, idempotent removal, versioned-bucket rejection and S3
failure behavior.

Separate identity/tenant HTTP servers, PostgreSQL, a local signed test JWKS and
Floci S3 passed real upload/overwrite/delete and cross-clinic/patient denial.
Headless Chrome then passed the actual file picker, stored preview, WebP
replacement, corrupt-image failure, profile save/reload, logo removal/reload and
390-pixel layout without horizontal overflow. Listing S3 after removal confirmed
zero clinic logo objects. Fixture mode also passed actual Save/Discard mouse
clicks, visible feedback, persisted profile/logo reloads, clinic separation and
storage-failure feedback without a false success or loss of unsaved edits. This is
local integration evidence, not deployed AWS/CloudFront verification.

Other clinic/staff/admin page integration remains A11; validated role navigation
and clinic selection remain U05.
