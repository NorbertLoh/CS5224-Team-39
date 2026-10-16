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

The adjacent video remains a local preview. It does not start a consultation,
change appointment status or admit a remote participant. PDF/download/order UI
remains separate work.

Configuration, service startup, integration checks and observed limitations:
[docs/records-frontend.md](../../../../../docs/records-frontend.md).
