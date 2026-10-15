# Clinical records UI (U12)

Doctor dashboard includes a C04 synthetic note/prescription preview. The displayed appointment, patient, and clinic IDs are fixture context, independent of the signed-in doctor's live appointments. No clinical API calls or persistent browser storage are used.

Run `npm ci`, `npm run dev`, sign in as a doctor, open `/doctor`, and scroll to Consultation notes and prescription. Enter a note, save it, add a medication and type its name, enter a positive whole quantity and placeholder instructions, save the draft, then issue it. Issuance locks content. Unsaved prescription changes must be saved before issuance. Reload resets all preview changes. There is no pricing, PDF generation, event publication or real record write. U11 #127 places the same form beside the doctor's video area at `/doctor/consultation`.

Real appointment selection, server authorization, audited reads, durable saves and API error handling remain R04 against R02. Notes remain editable during the in-progress fixture session after prescription issuance, as C04 restricts prescription edits rather than note edits.

`DoctorRecordForm` composes `ConsultationNoteForm`, `PrescriptionEditor` and `PrescriptionItemFields`. Note and prescription state stay local to their respective forms. The changed TypeScript/TSX files and record tests use Prettier 3.6.2 with `--single-quote --no-semi`.

Medication names are free-text preview entries. They have no fabricated catalogue medication IDs and are not sent to the C04 API. R04 must reconcile free-text input with the catalogue-linked backend contract before real integration.

Verification: frontend lint, TypeScript/build and automated tests. Typing, saving and issuance locking were browser-verified in the U11 consultation preview before this component-only extraction. No environment configuration changes.
