# RF05 local refinement verification

Draft PR #262 and issue #261 track the requested navigation and patient-workspace
refinements. No new dependencies or service configuration are required.

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
