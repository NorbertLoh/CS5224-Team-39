# Clinical records UI (U12)

The doctor consultation room (`/doctor/consultation`) includes a C04 synthetic note/prescription preview alongside the video area. The patient room excludes this form. The displayed appointment, patient, and clinic IDs are fixture context, independent of the signed-in doctor's live appointments. No clinical API calls or persistent browser storage are used.

Run `npm ci`, `npm run dev`, sign in as a doctor, open `/doctor/consultation`, and use Consultation notes and prescription. Enter a note, save it, add a medication and type its name, enter a positive whole quantity and placeholder instructions, save the draft, then issue it. Issuance locks content. Unsaved prescription changes must be saved before issuance. Reload resets all preview changes. There is no pricing, PDF generation, event publication or real record write.

Real appointment selection, server authorization, audited reads, durable saves and API error handling remain R04 against R02. Notes remain editable during the in-progress fixture session after prescription issuance, as C04 restricts prescription edits rather than note edits.

Verification: frontend lint, TypeScript/build and all 65 tests pass. Browser typing, draft save and issuance locking passed with a synthetic medication name. No environment configuration changes.


Medication names are free-text preview entries. They are not assigned catalogue medication IDs or sent to the C04 API. R04 must reconcile this input with the catalogue-linked backend contract before real prescription integration.
