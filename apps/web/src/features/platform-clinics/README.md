# U04 platform clinic administration

The platform clinic approval and commission page uses the real identity and
tenant services. No fixture fallback is used.

Route: `/platform-admin/clinics`. Requires a signed-in `platform_admin` identity.
Uses the existing frontend Cognito configuration and tenant/identity API proxies.

Sign in on the home page, then choose **Clinic approval and commission** under
Manage clinics, or open the route directly. Local platform account:
`platform@example.test` / `LocalDemo123!` (Floci only).
Follow [real backend setup](../../../../../docs/clinic-backend.md); no new
environment variables, migrations or dependencies are needed. AWS mode uses the
same existing API/Cognito configuration.

The page defaults to pending applications and supports all four status filters,
cursor pagination, approval, rejection, suspension and commission percentages
from 0 to 100 with two decimal places. Percentages are sent as integer basis
points. Rejection/suspension requires a plain-text reason; approval sends null.
The backend remains authoritative for roles and legal transitions. Successful
writes refresh clinic queries; failures retain edits and display safe messages.
Commission changes affect future payments, not historical snapshots.

Verification: frontend lint, typecheck/build and all 22 existing tests passed.
A live walkthrough used these feature API helpers through the Vite proxy against
FastAPI, PostgreSQL and Floci PKCE login. It verified persisted review transitions,
reason requirements, invalid transition conflicts, commission 0/12.34/100%,
invalid commission rejection, clinic/patient/doctor denial, signed-out handling,
status filtering and request cancellation. One new synthetic verification clinic
was left suspended with 0% commission; existing clinics were unchanged.
Browser layout/click interaction, multi-page pagination and AWS were not verified.

Issue #80 remains In progress until PR #81 is merged.
