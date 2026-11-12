# Doctor profile photos (RF53)

Active, approved doctors open **Doctor workspace → Profile** at
`/doctor/profile` to upload, replace or remove their public portrait. Choosing
a file saves it immediately. The same portrait appears in **Meet our doctors**
on every clinic storefront where that doctor is listed. Doctors without a photo,
and images that cannot load, retain the existing doctor icon.

Uploads accept PNG/JPEG up to 2 MiB, 4096 pixels per side and 16 million pixels.
Identity fully decodes the image, applies EXIF orientation, reduces it to at most
512×512, and stores a fresh JPEG without source metadata. Animated images,
mismatched formats, corrupt files and oversized uploads are rejected without
replacing the current photo. The frontend displays validation and save feedback.

## Ownership and API contract

Identity owns one bounded portrait per subject in `identity.doctor_photos`,
following its existing database-backed doctor upload pattern. This table and its
public route are separate from private licence evidence. No S3 bucket, public
document access, service credential or environment setting is added.

- `GET /me/doctor-profile` returns `{doctor_id, photo_id}` for the current doctor.
- `PUT /me/doctor-profile/photo` accepts raw PNG/JPEG bytes with the corresponding
  `Content-Type` and returns the saved identifiers.
- `DELETE /me/doctor-profile/photo` removes the current portrait (204, idempotent).
- `GET /doctors/{doctor_id}/photos/{photo_id}` returns the sanitized JPEG publicly,
  only while that subject is approved and has an active doctor membership.

All write routes derive the owner from the verified identity; clients cannot
select another doctor's subject ID. Replacements change the photo ID. Old photo
URLs, removed photos and photos belonging to revoked/ineligible doctors return
404. Responses retain identity's `Cache-Control: no-store` and use `nosniff`.

The internal identity directory and public tenant directory add nullable
`photo_id` to each `{doctor_id, display_name}` summary. Tenant validates the UUID;
the frontend constructs image URLs from its configured API base. Directory
membership, approval, clinic-state and cursor checks remain enforced. The
frontend invalidates cached clinic doctor lists after a successful profile edit.

## Migration and release

Identity requires migration `0007` and Pillow `12.3.0` (Python 3.10 compatible).
Install from `services/identity/requirements.lock.txt` or rebuild the identity
image. Back up the identity schema, then run `python -m alembic upgrade head`
from `services/identity` with the target service database configuration. Readiness
now requires `0007`. Downgrade refuses to discard stored photos; explicitly
remove them before downgrading if rollback is necessary.

Release tenant first so it accepts `photo_id`, then migrate/release identity and
release web. The tenant parser also accepts older summaries without photos, and
the frontend retains the icon for absent photos. Rebuild web with the existing
local/AWS API settings. API Gateway must explicitly allow public
`GET /api/v1/identity/doctors/{doctor_id}/photos/{photo_id}`; the general identity
proxy requires JWT authentication. Browser image requests do not attach the
application's bearer token. Uploads, removal and private evidence retain the
protected identity routes; identity still checks portrait eligibility.

## Verification

- Full identity PostgreSQL suite: **215 passed**, including upload, replacement,
  removal, persistent readback, directory projection, byte/dimension/format
  validation, private-evidence separation, authorization/revocation, metadata
  stripping and migration downgrade/upgrade checks.
- Full tenant PostgreSQL suite: **152 passed**, including public photo ID
  forwarding and rejection of unexpected private fields.
- Both service suites used fresh disposable PostgreSQL schemas and restricted
  service roles; Ruff checks and formatting passed.
- Frontend lint, production typecheck/build, probe typecheck, navigation and auth
  probes, and four video recovery checks passed. The navigation probe covers
  role-gated Profile routing, active navigation and storefront image/fallback
  markup.
- Headless Chromium with API fixtures passed invalid-file rejection, upload,
  replacement, reload, storefront display, removal/fallback and 390px layout.
  These browser fixtures verify UI behavior; they do not establish deployed
  integration. The real PostgreSQL API tests above verify persistence separately.

The local Tailscale demo was updated on 5 November 2026 at the user's request.
Identity was backed up to `.local/backups/RF53-identity-before-0007.dump`, migrated
from 0006 to 0007, and tenant/identity/web images rebuilt and restarted healthy.
Existing stopped Floci/Redis dependencies were started with their volumes intact.
Actual doctor sign-in and the Profile upload controls were verified at
`https://desktop-kdu3bpc.taila23b83.ts.net/doctor/profile`.
No portrait was changed during this live check. AWS rollout remains pending.
PR #380 merged on 5 November 2026 (`e94655a`); issue #379 is closed.

## AWS portrait routing correction (8 November 2026)

RF53 issue #379 was reopened for PR #397. Live investigation confirmed one approved
doctor with a persisted portrait: authenticated image GET returned 200 JPEG while
the ordinary public image GET returned 401, leaving the fallback icon after save.
The earlier demo reset is not the cause of this display failure.

Added the exact public GET route through the existing gateway integration. The
reviewed targeted Terraform plan created only that route, excluding the existing
unrelated CloudFront normalization. Applied to the existing Singapore demo with
its deployment inputs and image pins preserved. The current saved portrait now
returns 200 `image/jpeg` publicly and with authentication (15,016 bytes). No new
upload, database change or application rebuild was required.

Terraform regression assertions verify anonymous portrait reads and retained JWT
protection for identity writes/private evidence. All 14 mocked scenarios passed.
Issue #379 remains In progress until the fix PR is merged.
