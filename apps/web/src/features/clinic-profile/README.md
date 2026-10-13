# U02 clinic profile editor

Fixture-only clinic administrator previews at `/clinic-admin/clinics/:slug/profile`.
Edit name, description, colour, optional logo URL and consultation fee. Keep slug,
status and commission outside writable fields. Saves are local demo state; real
clinic access checks/navigation belong to U05 and tenant API integration to A11.

## Components

- `ClinicProfileEditor.tsx`: fixture lookup and per-clinic draft/saved state;
  validation, save feedback and discard-to-last-save behavior.
- `ClinicProfileForm.tsx`: clinic details, branding and fee fields plus actions.
- `ProfileField.tsx`: shared label, hint and field-error presentation.
- `BrandingPreview.tsx`: live visual preview, including missing-logo fallback.
- `profile.ts`: editable types, validation and tenant PATCH payload conversion.

The editor reuses U01's public-only fixture projection. No patient, clinical,
private membership or commission data is added to the browser. All clinic states
can be edited when supplied as fixtures; lookup does not require an active clinic.
The demo does not authenticate or establish administrator permissions.

## Demo behavior

Home-page clinic-administrator links open either seeded clinic. The form starts
with that clinic's values, and typing changes only the live editor preview.
Save validates the draft and updates a local saved snapshot. Discard restores
that snapshot. Leaving/reloading the editor restores the original fixtures;
neither action changes the public storefront or calls a backend. The page
explains this behavior and links to the original demo storefront.

Editable fields follow C02 and the tenant schemas: nonblank name up to 200
characters, plain-text description up to 2,000 characters, six-digit hex colour,
optional HTTPS logo up to 2,048 characters without whitespace/login details, and
a nonnegative SGD amount with at most two decimal places. Decimal input is
converted to integer minor units exactly, bounded by the safe JSON integer limit.
Blank logo becomes null. Slug, lifecycle state and commission are never included
in the update payload. Invalid submissions show field errors and focus the first
invalid input. No API or authorization cache is involved.

## Verification

From `apps/web`: `npm test`, `npm run lint`, `npm run build`.
All 22 frontend tests, lint, TypeScript and production build passed locally.
New checks cover exact cents, invalid/overflow amounts, logo URL restrictions,
name/description/colour limits, writable-only payloads and fixture isolation.

Headless Chrome verified live preview, all five field errors and first-error
focus, successful save/discard, broken-logo fallback, clinic separation, reset
on navigation/reload, missing clinic handling, home entry links and no business
API calls or browser exceptions. Desktop and true 390-pixel mobile views were
visually inspected; the mobile layout has no horizontal overflow.

No dependencies or environment configuration changes are required. U05/A11
must add real access checks, clinic selection and tenant API persistence before
this fixture editor becomes a live administration feature.
