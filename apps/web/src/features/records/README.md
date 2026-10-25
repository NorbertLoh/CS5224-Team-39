# Clinical records UI (R04)

Doctor: `/doctor/consultation`. Select a real appointment, save its note, choose
medications from its clinic's catalogue, save the draft, then issue it. Patient:
`/patient` lists the authenticated patient's prescriptions and loads audited
details on expansion. Pagination, empty/loading states and retry feedback use
real services; no synthetic prescriptions are imported by the production UI.

Saved records survive reload. Draft edits must be saved before issuance; issued
and voided content is locked. Writing requires an in-progress appointment and
server authorization. After any failed write, reload records to check the
server outcome before continuing. Switching appointments discards unsaved edits.

V04 pins this workspace to the booked video appointment and supplies explicit
authoritative start/completion actions. U17 adds an optional **Issue MC** draft,
inclusive date preview and private PDF generation after successful completion.
Save the MC draft before completing; an unconfirmed handoff can be retried from
the completed doctor page. See [MC setup and verification](../../../../../docs/medical-certificates.md).
U14 adds appointment document lists and downloads beside this workspace; see
[documents](../documents/README.md). Order UI remains separate work.

Configuration, service startup, integration checks and observed limitations:
[docs/records-frontend.md](../../../../../docs/records-frontend.md).

RF12 adds **Previous visit notes** below the current editing forms. Completed
visits are scoped to the selected patient, clinic and assigned doctor, ordered
newest first with older-page loading. Each keyboard-accessible disclosure loads
its saved note only when opened, through the existing audited note API. Missing
notes and request failures have explicit empty/retry states. Expanding history
never resets the current note, prescription or MC draft. No migrations or new
configuration are needed.

The clinical workspace now uses consistent cards, patient/session context and
clear save states. **Reload saved records** reloads the note, prescription and MC
from fresh server reads. It asks for confirmation only when any of those forms
has unsaved edits; **Keep editing** preserves them, while **Discard and reload**
restores the saved state. Reload is disabled during note/MC saves and prescription
save/issuance. Each form still saves independently. No API/configuration changes.

Local verification: lint, TypeScript and production build; live Tailscale checks
of clean reload without a prompt, dirty detection in all three forms, cancellation
and focus restoration, combined discard/reset, and the previous-note accordion.
Only unsaved test fields were changed; no note, MC or prescription was saved or
issued during the UI checks. One labelled demo catalogue item was added locally
so the prescription editor can be tested.
