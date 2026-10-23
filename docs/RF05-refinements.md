# RF05 local refinement verification

PR #262 merged on 23 October 2026 (commit `2f5a438`); issue #261 is closed.
The requested navigation and patient-workspace refinements are complete.
No new dependencies or service configuration are required.

## Legacy appointment names

New bookings already save patient, doctor and clinic names in scheduling's
appointment snapshot. Thirteen older local appointments had null snapshots.
Public directory lookups could not resolve the suspended synthetic clinics used
by earlier checks, so frontend directory fallback alone was insufficient.

On 23 October 2026, the missing snapshots on those 13 local appointments were filled
from their existing identity/tenant profiles. Existing snapshots were preserved.
The original booking-time labels cannot be reconstructed; these repaired fields
use current local profile names. A backup of the original nullable fields remains
in ignored `.local/RF05-appointment-name-backup.json`. All 16 local appointments
then had patient, doctor and clinic names. This local maintenance operation does
not add cross-service database access to application code and is not an AWS migration.

Appointment cards and details preserve saved names. Public directory fallback
supports other legacy records when names are available there; unavailable patient
names now also use a readable label rather than exposing a UUID.

ESLint, TypeScript/production build and local authenticated browser checks passed.
The patient API returned all 16 bookings with all three names; doctor and clinic
admin scopes each returned four fully named bookings. Cards and selected details
in all three workspaces displayed names, including patient names, with no UUID or
unavailable-name fallback in the checked fields.

## Patient appointment list

The patient workspace displays appointments across all loaded dates in time order,
with the Singapore date and complete time range on each card. The date dropdown
is removed; cursor pagination still offers Load more appointments when needed.
Doctor and clinic-admin views retain their date-based timetables.

Lint and production build passed. Authenticated browser checks verified all 16
local patient appointments across dates, each date/time label, no patient dropdown,
one selected card after each of 16 clicks, names and details. Doctor and clinic-admin
appointment card/detail checks also passed.

## Consultation join control

Patient and doctor appointment details keep Open video consultation visible.
Unavailable access renders a native disabled button with the opening date/time
or a status/payment explanation. Existing eligibility still requires the booked
participant, confirmed payment, an active appointment and the join window from
10 minutes before the start until the end. A local timer updates the control as
time passes; backend admission checks remain authoritative.

Lint/build and real local appointment-view checks passed. Browser UI checks with
intercepted appointment responses and a controlled clock verified disabled access
before opening, automatic enabling in the join window, automatic disabling at the
end, and disabled cancelled/completed/expired/no-show/unpaid states. These UI checks
did not modify bookings, start calls or establish new admission integration evidence.

## Appointment payment controls

Details label payment resolution in readable terms: Unpaid, Awaiting payment,
Paid, Refund review needed or Refunded. Only the owning patient sees Pay
consultation fee, and only for an unpaid held/pending-payment booking whose hold
has not expired. Existing checkout eligibility is reused; checkout still verifies
current billing state before payment. A timer removes the action at the deadline.

Lint/build and browser UI checks passed for active unpaid/pending holds, automatic
hold expiry, paid/expired/cancelled/completed/no-show bookings and refund states.
Payment-state UI checks used intercepted appointment responses and a browser clock;
they did not start checkout, create payments or change persisted booking/payment data.

## Upcoming and Past tabs

The patient appointment list now defaults to Upcoming. Future/ongoing active
bookings are ordered nearest first; ended, cancelled, expired, completed and no-show
bookings appear in Past, newest first. Tabs show counts of loaded bookings and
support keyboard navigation through the existing Radix dependency. Switching tabs
clears selection. A timer moves ended bookings to Past without reloading the page.

Lint/build and live three-role checks passed. All 16 current patient bookings were
correctly in Past, with date/time ordering, names, details and single selection
preserved. Controlled-clock UI checks additionally covered an empty Upcoming tab,
a future cancelled booking in Past, loading an upcoming booking from another page,
selection reset and automatic movement at the end time. Intercepted-response checks
did not change persisted bookings. The build passes with a bundle-size advisory.

## Dedicated patient pages

The patient navigation now links Appointments (`/patient`, default), Prescriptions
& medicines (`/patient/prescriptions`), Medication orders & delivery (existing
`/patient/medication-orders`) and Documents (`/patient/documents`). Each page uses
the existing live feature components. The default page no longer mounts the full
prescription/document lists. Appointment-specific documents remain available in
appointment details. Checkout, video, prescription-order and order-review links
retain their existing routes and query handling.

No new dependencies, configuration or migrations. Lint/build and live browser
checks passed for page links, active navigation, direct reloads and successful
backend reads (16 appointments, two prescriptions, two orders and three documents).
Signed-out visits to all four pages redirect to sign-in; a real doctor account
was denied the new patient records routes. Navigation wraps at a 390-pixel viewport.

## Prescription and medication-order accordions

Both patient pages use the Documents page's white bordered container, header with
refresh action and divided summary rows. A chevron indicates expandable content;
one item opens at a time, with native button keyboard support and labelled regions.
Prescription medicine/order actions and order payment/delivery controls are inside
the expanded row. Repeated medicine summaries are removed; the authoritative
prescription detail still shows quantities and instructions.

The patient order list replaces its previous side-by-side layout with inline
details. Direct order links expand their requested order, including an authorised
order outside the loaded list page. Prescription-order creation links, pagination,
live status queries and the clinic-admin order workflow remain available.

Lint/build and live browser checks passed for both lists, real detail loading,
single expansion, collapse, Enter/Space controls, 390-pixel layouts and clinic-admin
order selection. A deep-link check omitted the requested real order from the list
response and confirmed it still opened through its authorised detail endpoint.
No order, quote, payment or delivery was created during these checks.

## Expanded-content cleanup

Patient prescription content now starts with medicine quantities and instructions,
then one progress/price summary and the relevant order action. Technical metadata
is inside Prescription information. The patient order panel shows medicines once,
one payment/readiness summary and delivery guidance; references move into Order
information, and settled-order pricing is inside Cost breakdown. Nested duplicate
cards, repeated delivery steps and repeated status text are removed.

Pre-payment subtotal/delivery/total and the quote deadline remain expanded. Pending
payment, inconsistent success and refund-review/refunded guidance remain visible.
Existing quote/payment actions and staff layouts are preserved.

Lint/build and live accordion/deep-link/staff checks passed, including collapsed
references, one medicine list, keyboard controls and mobile screenshots. Additional
intercepted-response UI checks verified full pricing/address/payment controls for
an unpaid order, pending-payment guidance and upstream refund-review/refunded
messages. No quote or payment was requested during verification.

## Medication-order chronology

Patient medication orders now use newest-created-first API pagination, matching
the prescription list. The optional `sort=newest` parameter uses descending
creation time and order ID with a direction-bound cursor; the default API/staff
order remains oldest first. Direct-linked orders are positioned by date rather
than prepended above newer orders.

RF09 supersedes the default described above: both patient and clinic-admin order
histories now default to newest first. Explicit `sort=oldest` remains available.

Frontend lint/build and Python Ruff passed. All 42 fulfilment API tests passed in
a separate disposable database, including newest-first pages, timestamp ties and
cross-direction cursor rejection; the disposable database was removed afterward.
The fulfilment API was restarted and live checks verified newest-first pagination
and accordion order, with an older deep-linked order expanded in its proper place.
No migration or new configuration is needed.

## Documents grouped by visit

The standalone patient Documents page uses the shared accordion, grouping loaded
PDF metadata by appointment and clinic. Visit summaries show date/time, clinic,
doctor and available document count/types, ordered newest visit first. Prescription,
receipt and medical certificate PDFs appear only when issued, with their existing
ready/pending/failed and download states. Appointment-specific and staff lists stay
flat. Visit-context lookup failure does not hide the underlying document rows.

Lint/build and real local checks passed: three existing PDFs grouped into one
visit, names/counts, one-open/keyboard collapse, mobile layout and a signed download
validated as a PDF. Intercepted metadata checks verified same-visit merging across
cursor pages, separation of distinct visits, and no download controls for pending
or failed PDFs. No new documents were generated and no service access rules changed.

## Clinic-first patient navigation

Patient navigation is now Find a clinic, Appointments, Prescriptions, Orders &
delivery and Documents. Find a clinic links to `/#clinics`, the existing home-page
directory; signed-in patients retain navigation there and on clinic storefronts.
Patient password and hosted-PKCE sign-in default to Appointments after resolving
the backend identity's patient role. Other roles retain the existing destination;
failed destination lookup falls back to the home page with normal access checks.

Lint/build and real local browser checks passed for both patient sign-in paths,
doctor destination, public directory access, the five links and active states,
returning from directory to care pages and mobile wrapping. No new dependencies
or configuration are required.

## Receipt names

Document rows distinguish Consultation receipt from Medicines & delivery receipt
using the linked billing payment's purpose. The payment ID and tenant must match
the document. Requests use the existing authenticated billing endpoint and a
session-scoped query cache; unavailable or unsupported payment details retain the
generic Receipt label. Download button accessibility labels use the same name.

Build/typecheck and lint passed. Live browser checks verified both stored receipt
names and their download controls, plus generic fallback on a failed payment lookup.

## Merge preparation

Shared patient accordion, navigation, appointment controls and document row
components are retained. Receipt-purpose lookup and signed-download state now live
in focused `useDocumentName` and `useDocumentDownload` hooks, leaving DocumentRow
responsible for presentation. Prettier 3.6.2 formats the PR's changed TypeScript
files with single quotes, no semicolons and trailing commas. No formatter dependency
was added. Ruff formatting fixes the two fulfilment files flagged by CI.

Frontend lint/typecheck/build and fulfilment Ruff checks pass. The receipt browser
check also verifies the actual signed PDF download after the hook extraction.
Final GitHub CI passed for frontend lint/typecheck/build, backend Ruff and the
full fulfilment PostgreSQL/API suite, including the protected sentinel check.
