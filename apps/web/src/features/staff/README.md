# Staff management (U03)

`/clinic-admin/clinics/<tenant UUID>/staff` calls the existing identity membership
APIs through `apiFetch` and the shared access-token refresh helper. The feature
contains an API module, a page and a clinic context component. Email assignment uses
the identity POST membership route and migration `0002` for trusted account emails.
There are no runtime fixtures, new dependencies or environment settings.

The page shows the clinic name beneath its heading, read from the authenticated
tenant profile API by `ClinicContext.tsx`. A failed name lookup shows the tenant ID
and a retry action so the clinic context remains identifiable.

The list includes active/revoked memberships with cursor pagination. Assigning
an existing account by email or saving an edit replaces roles and activates access;
revocation keeps the row. Membership rows display names and emails; role edits and revocation use the stable account ID internally. Backend authorization and the last-admin guard
remain authoritative. Failures retain form edits and display safe messages.

Follow [local/AWS setup](../../../../../docs/clinic-backend.md). In local mode,
identity must use live tenant validation with no clinic fixture path configured.

Verification: frontend lint, typecheck/build and 22 existing tests passed. A live
walkthrough invoked these frontend API functions through Vite against local
FastAPI services, PostgreSQL and Floci-authenticated synthetic users. It checked
persisted role replacement, revoke/reactivate with the same membership ID,
last-admin revoke/demotion conflicts, nonexistent subject/clinic denial,
patient/doctor denial, platform listing and request cancellation. The synthetic
doctor's original roles/status were restored afterward. Browser layout and click
verification were unavailable because the browser tool had no connected browser;
AWS was not tested.

U05 follow-up verification: 111 identity PostgreSQL/API tests and 31 frontend tests
passed, with lint/typecheck/build and Python formatting checks. The additive local
migration and seeded-email backfill completed. A real Floci-authenticated Vite/API
check assigned an existing doctor by mixed-case email without changing membership
ID or roles, returned persisted names/emails, and rejected an unknown email.
