# Clinical records UI (U12)

The doctor consultation room (`/doctor/consultation`) includes a C04 synthetic note/prescription preview alongside the video area. The patient room excludes this form. The displayed appointment, patient, and clinic IDs are fixture context, independent of the signed-in doctor's live appointments. No clinical API calls or persistent browser storage are used.

Run `npm ci`, `npm run dev`, sign in as a doctor, open `/doctor/consultation`, and use Consultation notes and prescription. Enter a note, save it, add a medication and type its name, enter a positive whole quantity and placeholder instructions, save the draft, then issue it. Issuance locks content. Unsaved prescription changes must be saved before issuance. Reload resets all preview changes. There is no pricing, PDF generation, event publication or real record write.

Real appointment selection, server authorization, audited reads, durable saves and API error handling remain R04 against R02. Notes remain editable during the in-progress fixture session after prescription issuance, as C04 restricts prescription edits rather than note edits.

Verification: frontend lint, TypeScript/build and all 65 tests pass. Browser typing, draft save and issuance locking passed with a synthetic medication name. No environment configuration changes.


Medication names are free-text preview entries. They are not assigned catalogue medication IDs or sent to the C04 API. R04 must reconcile this input with the catalogue-linked backend contract before real prescription integration.

DoctorRecordForm composes ConsultationNoteForm, PrescriptionEditor and PrescriptionItemFields. Note and prescription state stay local to their respective forms. The records TypeScript/TSX files and tests use Prettier 3.6.2 with --single-quote --no-semi.

## Patient prescription preview (U13)

Sign in as a patient and open `/patient`. The Prescriptions panel shows the C04 synthetic issued prescription, independent of the logged-in account. Expand View details for medication dispensing units, plain-text instructions, appointment linkage, status and issue time in Asia/Singapore. Use Preview scenario to inspect empty/unavailable states. This panel has no API calls and does not imply real access authorization or audit completion. No active download/order buttons are shown before those services exist. Real integration remains R04; document UI remains U14.

U12 #118 and U11 #127 are merged; this branch targets main. No configuration changes.

`PatientPrescriptions` owns preview selection and expanded-detail state.
`PrescriptionSummary` renders the selectable summary, and `PrescriptionDetails`
renders metadata, medication quantities and instructions. These components and
the prescription tests use Prettier 3.6.2 with `--single-quote --no-semi`.

U13 refactor verification: frontend lint, TypeScript/production build, all 67
frontend tests, Prettier and `git diff --check` pass. Browser interaction remains
unverified; this change preserves the existing preview behavior.
