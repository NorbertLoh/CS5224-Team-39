# Staff management (U03)

`/clinic-admin/clinics/<tenant UUID>/staff` calls the existing identity membership
APIs through `apiFetch` and the shared access-token refresh helper. The feature
contains one API module and one page; there are no runtime fixtures, new backend
endpoints, migrations, dependencies or environment settings.

The list includes active/revoked memberships with cursor pagination. Assigning
an existing subject or saving an edit replaces roles and activates access;
revocation keeps the row. Subject IDs are displayed because the API does not
expose names or account search. Backend authorization and the last-admin guard
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
