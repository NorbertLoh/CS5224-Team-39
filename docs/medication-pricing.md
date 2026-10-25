# Prescription-specific medication pricing (RF12)

Clinic admins do not maintain a medication catalogue. Doctors type medication
names freely and issue prescriptions. Open the clinic's **Medicine & delivery**
page, then open the relevant medicine card to enter an SGD unit price for each medication on each
issued prescription. Quantity and line totals are shown; all items must be priced.
Use the clinic's existing system as a reference; this is manual price entry, not
an integration or synchronisation with that system.

Pricing is scoped by the selected clinic's Medicine & delivery page rather than
the Manage clinics dashboard. There is one combined list of medicine cards,
with no separate pricing section or side details panel. Each order shows **1. Medication
pricing** with its saved unit prices, quantities, line totals and medication total,
followed by **2. Medicine preparation** and **Mark medicine ready**. Existing-order
prices use its immutable order snapshot and remain locked. An issued prescription
can be priced before the patient opens an order; preparation is recorded on the
actual order once it exists. A prescription waiting for an order shows pricing
and a disabled preparation action within its own card; once the order is loaded,
the matching prescription and order are combined rather than repeated. The readiness, payment and delivery checks still run
on the server.

The queue exposes patient/visit metadata, medication names and quantities only.
It excludes consultation notes, MC details and prescribing instructions. Reads are
restricted to active owning-clinic administrators and are audited. No doctor,
patient, unrelated clinic or platform-only account can read the pricing queue.

Prices belong to one prescription and are never reused for a different patient's
prescription. Ordering/payment waits until every item has a clinic-entered price.
Prices lock when the patient opens a medicine order, preserving quote/payment
snapshots. Repeating an identical price save is safe; changing locked prices is
rejected. No default zero price is invented; an admin may explicitly enter 0.00.

Free-text names retain internal medication references for prescription/document
compatibility. These references require no clinic catalogue maintenance. Old issued
prescriptions/orders retain their legacy pricing behavior; new prescriptions and
existing drafts use prescription-specific pricing. The old catalogue APIs remain
compatible for legacy data but are not part of the clinic dashboard workflow.

## Setup

Back up clinical-records and fulfilment schemas before migration. Apply
**clinical-records 0006** and **fulfilment 0007** explicitly, then rebuild/restart
clinical-records, fulfilment and web. No environment variables or shared routing
changes. Clinical-records readiness requires its current migration head. Fulfilment
readiness also checks the new pricing table. Downgrades refuse to discard existing
prescription pricing policies or financial data. The local schemas were backed up
under ignored `.local/compose/` before these updates.

## Verification

136 focused fulfilment checks and 51 clinical checks passed against a separate
disposable database, with Ruff and frontend lint/TypeScript/production build.
Coverage includes per-prescription price gating, no cross-prescription reuse,
admin/tenant boundaries, exact line matching, unsafe totals, locks/replays,
legacy order compatibility and audited projection without private content.
Live Tailscale verification is recorded in the linked RF12 PR. No provider payment
or delivery is required to test pricing.

Live verification used a separate labelled synthetic issued prescription. Its order
was rejected while unpriced despite an existing legacy reference rate. The admin
entered SGD 0.75 for quantity 3 in the browser; the patient's unpaid order used
SGD 2.25 and subsequent price edits were rejected as locked. The admin response
contained no private prescribing instructions. No delivery quote, payment or
courier order was requested. The local catalogue-management screen is removed.
