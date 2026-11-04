# Clinic-admin prescription corrections (RF12)

In a clinic's Medicine & delivery card, choose **Add / edit medications**. An
active administrator of that clinic can add, rename or remove medicines, change
quantities/instructions, and record a correction reason. **Save prescription
correction** applies those changes to the clinical prescription, including for a
completed visit. It is not just a local dispensing override.

The original prescription and its items remain in history with status `voided`.
The replacement is issued with a new prescription ID, keeping the original
patient/doctor/appointment context. The correction records the administrator,
reason, timestamp and original/replacement IDs. Repeated identical requests return
the same replacement; a different correction of an already replaced ID returns
409. Further edits must target the current prescription. Removing all items
withdraws the prescription without issuing an empty replacement.

The replacement uses the existing prescription-issued event and document worker
to produce a new PDF. Prior PDFs remain historical references to their original
prescription IDs. New item IDs require fresh per-prescription prices; old prices
and order snapshots are not rewritten. No pricing, payment, quote or courier
request is made automatically by a correction.

## Orders and failures

Corrections are allowed before preparation, delivery quoting or checkout. An
untouched unpaid order is cancelled and retained with its original item/price
snapshot. The corrected prescription then appears as its own pricing card and
can be ordered again after pricing. Paid, pending, quoted, prepared or dispatched
orders cannot be silently changed through these controls.

Fulfilment commits a durable hold under the same prescription lock used for
order creation. It prevents an obsolete prescription from racing a new order,
including replays using old idempotency keys. Its existing order row is locked
while checking financial/preparation state. Clinical records then commits the
void/replacement and its issuance event in one local transaction. If that second
step fails, keep the same edits and retry; the hold is reusable. No distributed
transaction or automatic rollback of an already committed hold is claimed.

## Access and endpoints

- Clinical records GET `/clinics/{tenant_id}/prescriptions/{prescription_id}/correction`
  provides the selected prescription's medication details to an active owning
  clinic admin and audits the read. It does not grant access to consultation notes
  or MC details.
- Clinical records POST `/clinics/{tenant_id}/prescriptions/{prescription_id}/corrections`
  accepts `{reason, items}`. Items use the existing medication ID, quantity and
  instruction shape. All patient/doctor/appointment links are server-owned.
- Fulfilment POST `/clinics/{tenant_id}/prescriptions/{prescription_id}/prepare-correction`
  checks the same owning-clinic admin, validates the issued dispensing context,
  and reserves the correction before clinical records changes it.

Operational pricing projections still exclude prescribing instructions. Only
the explicit correction view exposes medication instructions to the newly
authorised administrator; clinical notes and MC endpoints retain their policies.

## Setup and verification

Back up clinical-records and fulfilment schemas. Apply **fulfilment 0008** and
**clinical-records 0007**, then deploy those APIs and web. Both downgrades refuse
to discard populated correction history. No new environment variables or event
schema are required. Clinical-records readiness expects 0007; fulfilment readiness
checks the hold table. The live schemas were backed up in the ignored local
RF12-before-medication-corrections.dump before migration.

Tests cover clinic ownership, revocation, add/edit/remove, complete withdrawal,
concurrent/idempotent revisions, original-history preservation, fresh issuance,
checkout/preparation locks, durable holds and stale order replays. The local
browser check uses a separate labelled RF12 correction demo order. It edits A's
quantity, removes B and adds C, then checks the corrected card and original
cancelled order. No real provider transaction is part of this check.
