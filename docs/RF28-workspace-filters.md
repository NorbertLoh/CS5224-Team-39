# RF28 workspace tabs, totals, search and filters

The user extended RF28 on 4 November 2026 to apply the application-review pattern
to clinic reviews, payments and appointments. The implementation stays in issue
#320 / draft PR #321 with the existing claim and shared-file ownership.

## Screens

| Screen                             | Tabs                                                          | Search                                                          | Date range             |
| ---------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------- |
| Platform doctor applications       | Pending review, Approved, Rejected, Resubmission required     | Licence name/number, authority, specialty or subject ID         | Submission date        |
| Platform clinics                   | All, Pending review, Active, Rejected, Suspended              | Clinic name, slug or clinic ID                                  | Registration date      |
| Clinic payments                    | All/consultation/medication purpose; all six payment statuses | Payment, patient, appointment, order or quote ID                | Payment creation date  |
| Patient/doctor/clinic appointments | Upcoming, Past                                                | Stored patient/doctor/clinic name or participant/appointment ID | Appointment start date |

Appointments additionally have a status filter. Clinic/appointment selectors and
staff-role inputs remain ordinary selection controls. Every screen provides
Apply search & filters and Reset. Applying filters resets pagination and selected
appointment details. Shared Radix tabs preserve keyboard navigation, focus and
tabpanel semantics; narrow layouts scroll the tabs horizontally.

Counters are database totals over the complete authorized result, not the number
of loaded cards. Search and date filters affect every count. Payment purpose
counters respect the selected history status, and status counters respect the
selected purpose. Successful-payment commission summaries keep their existing
financial definition, additionally honoring purpose/search/dates; history status
does not redefine those sums, as explained beside the summary.

## APIs and semantics

Existing lists accept optional `q`, `from` and `to`. Search is a literal,
case-insensitive substring, bounded to 200 characters; `%` and `_` do not act as
wildcards. Date parameters must be timezone-aware; `from` is inclusive and `to`
exclusive. The UI interprets dates in Singapore time and converts the selected
end date to the following midnight, so both selected dates are included.

Counts use the same predicates as their lists:

- Identity: `/platform/doctor-applications/counts` (platform only).
- Tenant: `/admin/clinic-counts` (platform only).
- Billing: `/payment-counts?tenant_id=...` (current owning clinic admins or
  platform admins; patient/doctor-only accounts cannot read clinic totals).
- Scheduling: `/appointment-counts` (current appointment access).

Scheduling list/count requests from the UI also specify `view_role` so accounts
with multiple roles get totals for the selected patient, doctor or clinic-admin
workspace. The server checks that role again and applies participant/clinic
predicates before searching/counting. Default API behavior without `view_role`
preserves the existing union of allowed metadata. Effective hold expiry and the
existing Upcoming/Past partition remain unchanged.

Clinic, billing and appointment signed cursors include active search/date/role
scope. Changing filters cannot reuse those cursors. Requests without filters
retain their previous scope semantics. Doctor application pagination resets when
filters change. No search or counter bypasses the existing role/tenant checks.

## Deployment and verification

No new migration or configuration is needed. Rebuild/restart identity, tenant,
billing, scheduling and web, preserving the existing Tailscale overlay. The shared
package adds `list_filters.py`; existing worker operations are unchanged. No
application data reset or provider transaction is part of this change.

Local checks: identity 199, tenant 136, billing 319 (plus 38 subtests), scheduling
267 (two skips), and shared-library/architecture 121 (12 environment skips) passed.
The billing/scheduling suites need their CI sentinel SQL; scheduling also needs
isolated Redis. Initial runs without those fixtures failed; complete reruns with
the documented CI fixtures passed. All database tests used the separate RF28
PostgreSQL container, not the application database. Frontend lint, typecheck,
probe typecheck and build passed, along with seven session checks and a focused
SGT inclusive-date encoding check. Tests cover full-page totals, literal search,
date boundaries, cursor scope, role/tenant isolation and multi-role appointment
views. Browser visual acceptance remains with the user at their request.

Authenticated checks through the existing Tailscale HTTPS origin passed for
platform clinic/application search and totals, denied patient admin totals,
clinic payment counts/search/commission filters, and patient/clinic-admin
appointment list/count/date/search agreement. The seeded doctor's unverified
workspace remained denied; authorized doctor behavior passed in the isolated API
suite. These live checks read existing business data only and revoked only their
own temporary login refresh tokens. No provider payment or courier call was made.
