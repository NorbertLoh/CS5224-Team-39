# Clinical records UI (U12)

Doctor dashboard includes a C04 synthetic note/prescription preview. The displayed appointment, patient, and clinic IDs are fixture context, independent of the signed-in doctor's live appointments. No clinical API calls or persistent browser storage are used.

Run `npm ci`, `npm run dev`, sign in as a doctor, open `/doctor`, and scroll to Consultation notes and prescription. Enter a note, save it, add the synthetic catalogue item, enter a positive whole quantity and placeholder instructions, save the draft, then issue it. Issuance locks content. Unsaved prescription changes must be saved before issuance. Reload resets all preview changes. There is no pricing, PDF generation, event publication or real record write.

Real appointment selection, server authorization, audited reads, durable saves and API error handling remain R04 against R02. Notes remain editable during the in-progress fixture session after prescription issuance, as C04 restricts prescription edits rather than note edits.

Verification: frontend lint, TypeScript/build and automated tests; browser interaction is unverified. No environment configuration changes.

U13 patient prescription view: implementation in progress on a stacked branch.
