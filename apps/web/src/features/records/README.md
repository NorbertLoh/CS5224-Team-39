# Clinical records UI (U12)

Doctor dashboard includes a C04 synthetic note/prescription preview. The displayed appointment, patient, and clinic IDs are fixture context, independent of the signed-in doctor's live appointments. No clinical API calls or persistent browser storage are used.

Run `npm ci`, `npm run dev`, sign in as a doctor, open `/doctor`, and scroll to Consultation notes and prescription. Enter a note, save it, add the synthetic catalogue item, enter a positive whole quantity and placeholder instructions, save the draft, then issue it. Issuance locks content. Unsaved prescription changes must be saved before issuance. Reload resets all preview changes. There is no pricing, PDF generation, event publication or real record write.

Real appointment selection, server authorization, audited reads, durable saves and API error handling remain R04 against R02. Notes remain editable during the in-progress fixture session after prescription issuance, as C04 restricts prescription edits rather than note edits.

Verification: frontend lint, TypeScript/build and automated tests; browser interaction is unverified. No environment configuration changes.

U13 patient prescription view: implementation in progress on a stacked branch.

## Patient prescription preview (U13)

Sign in as a patient and open `/patient`. The Prescriptions panel shows the C04 synthetic issued prescription, independent of the logged-in account. Expand View details for medication dispensing units, plain-text instructions, appointment linkage, status and issue time in Asia/Singapore. Use Preview scenario to inspect empty/unavailable states. This panel has no API calls and does not imply real access authorization or audit completion. No active download/order buttons are shown before those services exist. Real integration remains R04; document UI remains U14.

The U13 branch is stacked on U12 for shared fixture types; merge/rebase U12 first. No configuration changes.
