# U08 appointment views

Fixture preview on `/patient`, `/doctor` and `/clinic-admin`. Select a demo
patient, doctor or clinic, then a date. Each cell covers 30 minutes in Singapore
time; select an appointment to read its details. Empty cells represent no
appointment in this preview, not bookable availability.

Uses `dev/fixtures/telelink.json` unchanged. Patient previews include only their
own appointments, doctor previews require assignment and active clinic membership,
and clinic previews include only the selected clinic. These frontend fixture
filters are demonstrations; S07 must connect authenticated scheduling list/detail
APIs and enforce server authorization. No live booking/payment actions are offered.

No new configuration. Run `npm test`, `npm run lint` and `npm run build` in
`apps/web`. Browser walkthrough: change preview context/date, select appointments,
check empty days and multiple appointments at the same time, and use keyboard
navigation and a narrow viewport.
