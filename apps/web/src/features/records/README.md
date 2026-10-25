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

Fulfilment migration 0006 is required for typed medication pricing; no new environment variables. See [records setup](../../../../../docs/records-frontend.md),
[MC setup](../../../../../docs/medical-certificates.md) and [documents](../documents/README.md).
The patient `/patient` view continues to use real authorised prescription/document APIs.

RF12 verification: frontend lint, TypeScript and production build passed. Live
Tailscale checks covered note debounce/latest text, clean reload, all three dirty
states, discard/cancel/focus restoration, history expansion and keyboard interaction.
A separate synthetic consultation verified database preservation for blank notes
and incomplete MC/prescription inputs, and all three valid autosaved drafts survived
a full browser reload. No MC/prescription was issued, visit completed, payment made
or delivery sent. Labelled synthetic visit/note/catalogue examples remain local.

Medication entry is now an unrestricted name textbox. Valid autosaves reuse or
register a clinic-owned unpriced medication reference. Clinic admins price these
under Medications & prices on their existing dashboard. Prescriptions may be
issued before pricing, but order/quote creation waits for every medicine to be
priced. Setup: [medication pricing](../../../../../docs/medication-pricing.md),
including fulfilment migration 0006. Prescription/event/document IDs are unchanged.
