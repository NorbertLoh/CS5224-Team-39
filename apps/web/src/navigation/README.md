# Workspace navigation

`AppShell.tsx` owns the shared header, sign-in/out controls, identity checks and
one contextual section bar. `WorkspaceSwitcher.tsx` replaces the separate role
links on every signed-in page. `workspaces.ts` derives available workspaces and
the selected workspace from the current identity and route. Roles come from
`/identity/me`, never browser role storage or Cognito groups. Identity refreshes
on page load, focus and every 30 seconds; API checks remain authoritative.

Patient-only accounts hide the workspace dropdown and retain patient navigation.
Other accounts get one workspace dropdown with the current role's name, icon and
checkmark. It contains granted workspaces and Browse clinics. Doctor and clinic
registration links stay on the clinics homepage, outside the dropdown. Doctor
application is a separate onboarding destination, not a granted clinical role.
Before approval and active clinic membership, accounts can open application
status but have no doctor schedule links.

`WorkspaceNavigation.tsx` provides consistent section bars, horizontally scrollable
links on narrow screens, and a single bottom-border active/focus indicator.

- Patient: Find a clinic, Appointments, Prescriptions, Orders & delivery,
  Documents and My profile. The directory and public storefronts retain patient
  navigation for signed-in patients. Checkout is an appointment action.
- Doctor: Appointments, Availability and Verification. Clinic selection lives in
  the bar; availability defaults to the first active doctor clinic. Verification
  is account-wide, preserving validated clinic context through `?clinic=<UUID>`.
  Consultation pages do not mark a list link current or show a clinic picker.
- Clinic admin: My clinics and Appointments at the workspace entry. Selecting a
  clinic shows one management bar: Clinic profile, Staff, Appointments, Payments,
  Medicine Pricing, Medicine Delivery and Settings. The medicine tabs show red
  counts for prescriptions with missing prices and paid orders awaiting preparation.
  The named clinic selector retains the section
  when changing clinics; All my clinics returns to the list. The unscoped
  appointment page retains its existing per-clinic schedule selector.
- Platform admin: Clinics and Doctor applications. Platform administrators retain
  explicit tenant API access to clinic profile, staff and payments without clinic
  membership. Their management bar links back to platform clinics and hides the
  membership-only appointment, medicine/delivery and settings pages.

Switching directly between doctor and clinic-admin workspaces preserves the URL's
clinic only if the destination role has active membership there. Otherwise it
opens that workspace's entry page. No clinic/role selection is persisted across
users in browser storage. Revoked memberships never enter the selector. Route
access checks block unauthorized direct URLs before feature content mounts.

`access.ts` owns exact route parsing and access rules. `AppRoutes.tsx` maps routes
to features. Patient and doctor consultations remain appointment actions with
existing admission checks. All existing page URLs and API behavior are retained.
No new configuration, dependencies or migrations.

Verification:

- Frontend lint, typecheck, probe typecheck and production build.
- `node dev/run_frontend_probe.mjs check_navigation_frontend.mts`: role/route
  selection, multi-role headers, hidden patient-only switcher, doctor onboarding,
  single section bars, scoped links, revoked membership exclusion, platform
  exceptions, consultation and signed-out/denied rendering. It renders React on
  the server with synthetic identity fixtures and makes no API calls.
- `node dev/check_auth_session.mjs`: existing session checks.
- Tailscale web rollout and HTTP source verification. Visual/mobile browser
  acceptance stays with the user at their request.

Setup: [local backend](../../../../docs/clinic-backend.md),
[authentication](../../../../docs/authentication.md),
[doctor verification](../../../../docs/RF28-doctor-verification.md),
[patient profile](../../../../docs/patient-profile.md),
[clinic pickup settings](../../../../docs/clinic-pickup-settings.md).

Navigation attention indicators use red text/badges for work needing action and
amber for waiting or progress. They retain one bottom active underline, without
a second focus line. Badges include text and accessible descriptions, so their
meaning does not depend on color.

- Doctor verification: Action needed for no application, rejection or revocation;
  In review for pending; no badge for approved.
- Patient Appointments: Payment due counts only this patient's live held or
  pending-payment bookings with a future hold deadline and appointment end.
  Refunded/refund-required, cancelled and expired bookings are excluded.
- Patient Prescriptions: Red count for issued medicine prescriptions awaiting
  payment, including those without an order only once all medicine prices are
  available. Unpriced prescriptions show Awaiting pricing in the patient list.
- Patient Orders & delivery: Needs attention for unpaid orders, exceptions or
  refund review; In progress for pending payment confirmation, paid/preparing,
  submitting or dispatched orders. Completed/refunded and ordinary cancelled
  orders do not retain highlights. Red action takes precedence over amber progress.
- Platform Clinics and Doctor applications: Pending badges use the existing
  unfiltered aggregate review counts, independent of page search/filter state.

Queries are scoped to the mounted workspace and session, refresh on focus and
every 30 seconds, and share existing application/review cache keys and invalidation.
Patient list aggregation follows every cursor, uses explicit patient appointment
view and checks patient ownership for orders on mixed-role accounts. The existing
fulfilment list may include other records authorized by an admin role; only the
current patient's records contribute. Navigation reads the lightweight order list
without delivery-detail fan-out. This prototype uses paginated list aggregation
for patient badges; a dedicated server aggregate can reduce cost at larger scale.
Loading/failed checks omit their badges and do not claim zero outstanding items.
Independent queries let one service's failure leave other indicators available.
No new endpoints, data writes, migrations, settings or dependencies.

Attention badges display coloured numbers only (one for a single verification application). Status labels and descriptions remain in tooltips and screen-reader text.
