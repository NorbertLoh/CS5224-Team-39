# U05 navigation

- `access.ts`: exact route parsing, role rules and active membership selection.
- `AppShell.tsx`: one shared login/logout control and identity access gate.
- `RoleNavigation.tsx`: granted role links.
- `AppRoutes.tsx`: route-to-feature mapping; forms and API calls stay in their features.

Patient navigation starts with Find a clinic (`/#clinics`, the existing public
directory), followed by Appointments, Prescriptions, Orders & delivery and Documents.
The four protected pages are `/patient` (appointments, default),
`/patient/prescriptions` (prescriptions and medicines), the existing
`/patient/medication-orders` (orders and delivery), and `/patient/documents`.
The patient feature owns the shared page navigation and records-page composition.
Direct links retain the normal authentication/identity gates. Checkout and video
remain appointment actions, and medication order query links keep their existing URLs.

Roles come from `/identity/me`, never Cognito groups or browser role storage.
Identity is refreshed on page load, window focus and every 30 seconds. Protected
features wait for a successful identity lookup; a failed refresh or revoked
membership blocks them. Backend checks still enforce every protected API operation.
Signed-out protected-page visits replace the current browser history entry with
`/sign-in` before rendering feature content. Public pages remain accessible, and
successful patient sign-in opens `/patient` after checking the backend identity.
Other roles retain the home-page destination. Signed-in patients also keep their
workspace navigation on the public directory and clinic storefronts.

The clinic choice is the URL, checked against current active memberships for the
route's role. Clinic administrators choose a named clinic from the Manage clinics
cards in their workspace. The navigation contains role links only, without a
duplicate clinic dropdown. There is no persisted clinic choice to carry between
users. Platform administrators
select clinics from the existing paginated platform list and retain the tenant
APIs' explicit clinic administration access without a membership.

Routes: `/patient`, `/doctor`, `/doctor/clinics/<UUID>`, `/clinic-admin`, existing
clinic profile/staff routes, and existing platform clinic routes. Unknown paths
show Page not found. Patient entry uses the real public clinic directory. Doctor
entry validates clinic membership and states that future availability/consultation
features are pending; U05 does not implement those workflows.

No new configuration or dependencies. Use the existing
[local backend setup](../../../../docs/clinic-backend.md) and
[authentication setup](../../../../docs/authentication.md).

Verification (14 October 2026): frontend tests, lint and production build passed.
Tests cover role restrictions, arbitrary/revoked/multiple clinic choices, protected
feature mounting, logout state and failed identity refresh. Live local checks used
four Floci PKCE logins, real identity/tenant APIs, allowed clinic/profile reads,
denied patient/doctor platform reads and hosted logout/token revocation. Access
rules were also run against the four live identity responses. Browser interaction,
visual/mobile layout and AWS integration were not verified: no browser surface was
available through the session's UI tool.
