# Clinical records UI (R04 / RF12)

The doctor records workspace is pinned to the booked consultation at
`/doctor/consultation?appointment_id=<id>`. It groups the patient/session context,
consultation note, optional MC, prescription, previous visits and documents.
Writes require the assigned doctor's current access and an in-progress visit.

## Draft autosave

Notes, MC selections and prescription drafts autosave after a one-second pause.
There are no manual Save buttons. Each section shows waiting, saving, saved,
incomplete or error feedback. Wait for Saved before completing the consultation.
Prescription issuance and consultation completion remain explicit actions.

Only nonblank notes, valid MC selections and complete catalogue-linked prescription
items are saved. The API requires at least one prescription item; removing all
items does not overwrite an existing draft. Clearing a saved note likewise does
not erase it. Issued/voided prescriptions and finalized MCs remain locked.

Saves run serially per form. Queued saves cancel on edits/unmount; newer note text
survives an earlier response. Failed writes do not silently retry. Note/prescription
errors require reloading saved records to check the outcome. MC fields remain
available with an explicit Retry autosave action. Navigation warns while changes
are unsaved; autosave does not guarantee a write before closing the browser.

## Reload and history

Reload saved records fetches fresh note, prescription and MC snapshots. It asks
before discarding unsaved edits, and is disabled during saves/issuance. Keep editing
preserves the draft and restores focus to Reload. Each form still saves separately.

Previous visit notes lists earlier completed visits for the same patient, clinic
and assigned doctor, newest first with older-page loading. Expand a visit with
mouse or keyboard to fetch its saved note through the existing audited API.
History does not reset current edits or broaden access to other doctors' notes.
Missing notes and failed requests have explicit empty/retry states.

## Setup and verification

Clinical-records 0006 and fulfilment 0007 are required for prescription pricing; no new environment variables. See [records setup](../../../../../docs/records-frontend.md),
[MC setup](../../../../../docs/medical-certificates.md) and [documents](../documents/README.md).
The patient `/patient` view continues to use real authorised prescription/document APIs.

RF12 verification: frontend lint, TypeScript and production build passed. Live
Tailscale checks covered note debounce/latest text, clean reload, all three dirty
states, discard/cancel/focus restoration, history expansion and keyboard interaction.
A separate synthetic consultation verified database preservation for blank notes
and incomplete MC/prescription inputs, and all three valid autosaved drafts survived
a full browser reload. No MC/prescription was issued, visit completed, payment made
or delivery sent. Labelled synthetic visit/note/catalogue examples remain local.

Medication names remain unrestricted text. Once the doctor issues a prescription,
the clinic admin enters each medication's price for that prescription under
Prescription pricing. No catalogue maintenance is required. See
[pricing setup](../../../../../docs/medication-pricing.md): clinical-records 0006
and fulfilment 0007 preserve legacy issued/paid behavior and require explicit
prices for new/draft prescriptions.

The final per-prescription pricing check separately issued a labelled synthetic
prescription and opened an unpaid medicine order to verify its specific prices
and lock. It made no payment, delivery quote or courier request. See pricing setup
for the final workflow; the earlier autosave-only checks did not issue documents.

Autosave focus regression: draft saves keep note/MC/prescription fields enabled
and mounted, preserve raw text/caret and keep prescription rows in their current
order. Save acknowledgements update only saved snapshots and medication IDs;
newer edits remain queued for a subsequent serial save. Background records reads
do not replace loaded forms with a loading screen. Explicit issuance/read-only
locks still apply. An isolated browser check using the production components and
800 ms delayed responses verified retained focus, caret 2 -> 3, pending-request
edits and two prescription rows staying in order across saves for all three forms.
The temporary check did not call real clinical APIs and is not a production route.

Doctor lifecycle controls: **Start consultation** appears above the records before
clinical start. Once in progress, **End consultation** appears below records,
history and documents. End is disabled while any note/MC/prescription changes are
unsaved or saving. Existing start-time guards, completion handoff and separate
video Leave behavior are preserved. Browser verification on a separate synthetic
visit covered confirmed/start visibility, start -> in-progress transition, bottom
End after Documents, disabled End for unsaved text and re-enabled End after saving.
The visit was not ended. Frontend lint, TypeScript and production build passed.

Visit documents is a native keyboard-accessible disclosure, closed by default in
the doctor records workspace. Expand it for the existing document status, refresh
and PDF download actions. End consultation remains below it. Verified default
collapse, Enter expansion/collapse and refresh availability on the live local
consultation; lint, TypeScript and production build passed. No API changes.
