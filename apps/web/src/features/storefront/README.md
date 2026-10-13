# U01 clinic storefront

Public fixture previews are served at `/clinics/demo-clinic-a` and
`/clinics/demo-clinic-b`. U01 covers branding, consultation price, active doctors,
responsive presentation and unknown/inactive-clinic handling.

Use only public clinic and doctor fields derived from the agreed
`dev/fixtures/telelink.json` dataset. Booking is a clearly labelled future step;
U07 owns the slot picker and A11 owns live tenant API integration.

## Data and implementation

`fixtures.json` is a public-only projection of the shared dataset: clinic ID,
slug, name, state, branding, consultation price and active doctors' IDs/names.
The browser never imports the full shared fixture with patients and clinical
records. When shared clinics or staff change, update this public projection;
`tests/storefront-fixtures.test.ts` checks parity, doctor membership scope and
the exclusion of private fields.

`ClinicStorefront.tsx` handles clinic lookup, colour and page layout. Small
components render the header, introduction, consultation card, doctor list,
footer and unavailable page. They share a `StorefrontClinic` type derived from
the public fixture shape and receive their data through props. The
home page links to both previews. Normal links support direct entry, reloads and
browser history without additional routing dependencies. Unknown, inactive and
malformed clinic paths display an unavailable page. The preview is public and
does not require a login.

The booking control is disabled and explains that appointment selection and
payment are not available yet. It creates no holds, appointments or payments.
These fixtures do not establish live clinic or booking integration.

## Verification

From `apps/web`, run `npm test`, `npm run lint` and `npm run build`.
All 17 frontend tests, lint, typechecking and production build passed locally.
Headless Chrome verified both clinic colours/prices/doctor lists, revoked and
other-clinic doctor exclusion, the disabled booking notice, home/storefront
navigation, doctor anchor navigation and unknown/malformed route handling.
Desktop rendering and a true 390-pixel mobile viewport were visually inspected;
the mobile page has no horizontal overflow. The interactive browser tool could
not initialize, so verification used the installed Chrome in headless mode.

No new dependencies, environment variables or backend configuration are required.
Live clinic API wiring remains A11; appointment selection remains U07.
