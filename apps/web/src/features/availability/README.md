# U06 doctor availability fixture editor

Sign in with an active doctor membership and open `/doctor` (Doctor in the role
navigation). Existing `/doctor/clinics/:tenantId` routes mount the same explicitly
labelled fixture preview after the shell's membership check. Demo clinic/doctor
selection is independent of the signed-in account and selected real clinic.
It never reads or writes scheduling APIs.

Run the frontend with the existing `npm run dev` setup. Authentication/identity
services are still needed for the protected doctor workspace; no extra environment
variables or services are required by the editor.

The editor uses the shared synthetic dataset in `dev/fixtures/telelink.json`.
Slots move by whole days so the earliest fixture day is tomorrow in Singapore.
Active fixture doctor memberships determine the choices. Changes are kept in
component memory across demo clinic/doctor selections and reset on page reload.
There is no simulated save to a server or durable browser persistence.

Dates and times always use Asia/Singapore, including browsers in other timezones.
Creating a slot produces a future 30-minute UTC interval. Overlaps are rejected
for that doctor across both clinics, while adjacent intervals are allowed.
Unavailable slots and past slots cannot be removed. To change an available time,
remove the old slot and add its replacement. Empty days, validation errors and
successful changes have explicit feedback. Data loads synchronously from the
bundled fixture, so this editor does not simulate network loading or failures.

Verification (14 October 2026): all 38 tests passed with `npm test`;
`npm run lint` and `npm run build` (including TypeScript) passed from `apps/web`.
Focused tests cover timezone conversion, invalid dates, interval boundaries,
cross-clinic conflicts, membership choices and removal protection. Browser
interaction and live scheduling integration are separate checks; S07 replaces
fixture data and client-side validation with authenticated scheduling API calls
and authoritative server conflicts.
