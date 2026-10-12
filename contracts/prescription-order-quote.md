# C04: prescriptions, orders, quotes and trusted pricing

Proposed contract using [C01](api-conventions.md) and [C05 events](events.md),
coordinated with [C02 access](https://github.com/NorbertLoh/CS5224-Team-39/pull/36)
and [C03 payments](https://github.com/NorbertLoh/CS5224-Team-39/pull/37).
Consumer review is pending. R01-R04/D01-D07/B06/P01-P03 implement these APIs;
this document does not implement clinical care, pricing or provider integration.

## Prescription and clinical-record ownership

Clinical records owns notes and prescriptions. Prescription requires
`prescription_id`, `tenant_id`, `appointment_id`, `patient_id`, `doctor_id`,
`status` (`draft`, `issued`, `voided`), `items`, `issued_at` (instant or null),
`created_at`, `updated_at`. Each item requires `prescription_item_id`,
`medication_id`, `quantity` (positive integer dispensing units), `instructions`
(plain text) and `display_name` (snapshot). Initial prototype uses the owning
clinic's fixed catalogue, no substitutions/partial fills or arbitrary patient
quantities. Instructions are supplied by the authorized doctor; fixtures have
nonclinical placeholder text. A prescription has no trusted charge total.

Notes require `note_id`, appointment/tenant/patient/doctor IDs, `text` (plain text),
created_at/updated_at. Only the assigned active clinic doctor can write during
in_progress consultation; reads follow C02 patient/assigned-doctor policy and
are audited. Clinic/platform admins receive no note or instruction content.

| Clinical route (prefix `/api/v1/clinical-records`) | Body / response | Policy |
| --- | --- | --- |
| PUT `/appointments/{appointment_id}/note` | `{ "text": "..." }`; note, 201 new / 200 update | Assigned active doctor, appointment in_progress |
| GET `/appointments/{appointment_id}/note` | Note, 200 | Own patient or assigned active doctor; audit |
| POST `/appointments/{appointment_id}/prescriptions` | `items` with medication_id, quantity, instructions; draft, 201 | Same writing policy; server supplies links/name/item IDs; one non-voided prescription per appointment |
| PATCH `/prescriptions/{prescription_id}` | Full `items` replacement; draft, 200 | Same doctor while draft/in_progress |
| POST `/prescriptions/{prescription_id}/issue` | Empty body; issued prescription, 200 | Same doctor/in_progress; nonempty valid items; repeated issue returns same resource/event identity |
| GET `/prescriptions/{prescription_id}` | Prescription, 200 | Own patient or assigned active doctor; audit |
| GET `/prescriptions` | Optional appointment_id; C01 pagination ordered created_at, prescription_id ascending | Same scoped read policy |

Issuance freezes content and commits prescription_issued.v1 to the same outbox
transaction. Voiding is an authenticated operator workflow, outside the initial
public API: it must check that no accepted/paid/dispensing order exists and record
reason/audit. Draft/voided prescriptions cannot create orders. Do not silently
void an already-paid prescription or edit an issued prescription's quantities.
No broad patient-history access is implied by clinic membership.

Fulfilment obtains a minimum dispensing projection through service-only GET
`/api/v1/clinical-records/internal/prescriptions/{prescription_id}/dispensing`:
prescription/appointment/tenant/patient IDs, status and item ID/medication ID/quantity.
It excludes notes/instructions. Allow only authenticated fulfilment/billing callers
with validated patient/tenant purpose; document service has a separately authorized
full issued projection for PDF generation. Public ingress excludes internal routes.
No service reads or writes another service's database tables.

The full issued projection uses service-only GET
`/internal/prescriptions/{prescription_id}/document` under the clinical-records
prefix, allowing only authenticated document-service callers for generation.
Patient PDF retrieval still goes through document authorization/auditing below.

## Catalogue, order and quote shapes

Fulfilment owns the catalogue and orders. A catalogue item requires `medication_id`,
`tenant_id`, `display_name`, `unit_label`, `unit_price` (C01 SGD Money), `active`,
`updated_at`. Clinic admin controls price/active status; prescription display name
does not establish price. A doctor selects active medications, not patient-supplied
prices. An order price is frozen at successful checkout reservation; before that,
the server refreshes current catalogue prices on each new quote.

Order requires `order_id`, `tenant_id`, `prescription_id`, `appointment_id`,
`patient_id`, `status` (`awaiting_payment`, `paid`, `submitting`, `dispatched`,
`delivered`, `cancelled`, `exception`), `medicine_status` (`not_ready`, `ready`),
`payment_status` (`unpaid`, `pending`, `succeeded`, `refund_required`, `refunded`),
`payment_id` (UUID or null), `quote_id` (UUID or null), `delivery_id` (UUID or null),
`items`, `medication_subtotal`, `delivery_fee`, `total`, `created_at`, `updated_at`.
Each item requires `prescription_item_id`, `medication_id`, `display_name`,
`quantity`, `unit_price`, `line_total`. Delivery fee/total are null before a quote;
all other amounts are C01 SGD Money. `line_total = quantity * unit_price` and
subtotal is the sum. Quantity must exactly match the issued dispensing projection.
Admin operational order responses exclude instructions, notes and full addresses.

Quote requires `quote_id`, `order_id`, `tenant_id`, `status` (`active`, `accepted`,
`expired`, `superseded`), `medication_subtotal`, `delivery_fee`, `total`,
`expires_at`, `created_at`. All amounts are trusted immutable SGD snapshots and
`total = medication_subtotal + delivery_fee`. Origin is owning clinic's configured
dispatch address; destination is a validated patient-supplied structured address
stored privately with the quote (`address_line`, `postal_code`, `country_code=SG`).
Price/address changes require a new quote and invalidate prior unaccepted quotes.
Provider references and address payloads never appear in C05 events/general logs.

| Route (prefix `/api/v1/fulfilment`) | Body / response | Policy |
| --- | --- | --- |
| GET `/clinics/{tenant_id}/catalogue` | Active items, C01 pagination ordered display_name, medication_id ascending | Active owning-clinic doctor/admin; not a public medical catalogue |
| PUT `/clinics/{tenant_id}/catalogue/{medication_id}` | display_name, unit_label, unit_price, active; item, 201/200 | Active owning-clinic admin; server validates SGD/nonnegative amount |
| POST `/orders` | prescription_id; order, 201 new / 200 existing | Own patient; one order per issued prescription, including retries |
| GET `/orders/{order_id}` | Order, 200 | Own patient or active owning-clinic admin; platform operational view, no clinical data |
| GET `/orders` | Optional tenant_id/status; C01 pagination ordered created_at, order_id ascending | Same scoped policy |
| POST `/orders/{order_id}/quotes` | destination structured address; quote, 201 | Own patient; unpaid, no active pending payment; server obtains provider fee and refreshes catalogue snapshot |
| GET `/quotes/{quote_id}` | Quote, 200 | Own patient or active owning-clinic admin; operational fields only |
| POST `/orders/{order_id}/ready` | Empty body; order, 200 | Active owning-clinic admin; issued prescription, valid active order; repeated ready is safe |
| POST `/orders/{order_id}/cancel` | reason; order, 200 | Own patient or active clinic admin before submitting; pending checkout is closed/reconciled before release |
| GET `/deliveries/{delivery_id}` | Delivery, 200 | Own patient or active clinic admin; platform operational view |

POST orders/quotes and medication checkout require C03 Idempotency-Key rules.
Catalogue price updates do not modify accepted quote/order/payment snapshots.
Catalogue inactive item or missing current price -> 409 `medication_unavailable`.
Repeated order creation never bypasses one-order-per-prescription, including
cancelled orders; reopening/replacement is a future explicit workflow.

## Checkout acceptance and expiry

POST `/api/v1/billing/medication-checkouts` accepts ONLY `order_id`, `quote_id`
and C03 idempotency header. Return `{payment, checkout_url, expires_at}` as C03.
Owning patient only. Billing does not accept totals, prescription quantities,
delivery prices, readiness or provider IDs from the browser.

Billing calls service-only POST
`/api/v1/fulfilment/internal/orders/{order_id}/checkout-reservation` with
`quote_id`, `payment_id`, authenticated subject context. Fulfilment atomically
checks tenant/patient/issued prescription, quote ownership and active status,
`server_now < expires_at`, order unpaid and no different accepted attempt. It
sets quote accepted, order payment pending and binds payment_id; returns trusted
items/subtotal/fee/total and original deadline. Repeat of the same payment is safe.
Billing snapshots those values and tenant commission; C03 commission excludes
delivery fee. Provider checkout deadline cannot exceed the quote's expiry.

Local quote expiry is min(provider fee validity, server_now + 10 minutes).
If the provider does not supply a usable validity interval, the adapter must
obtain a verifiable fee or explicitly label a demo adapter; do not invent real
provider guarantees. Accepted snapshots remain immutable, but payment processing
at/after deadline must not start delivery blindly. On verified late success,
fulfilment records payment truth then sets order exception/payment refund_required
for manual full-refund resolution; a new provider quote cannot silently increase
the paid charge. The same applies to success on a cancelled order or superseded
quote. Failed attempts can release acceptance and retry only before deadline,
with a reconciled failed payment; pending/uncertain attempts block re-quoting.

If timely payment succeeds but medicine is ready later than provider quote expiry,
revalidate delivery fee/route before submission. Submit only when the fee still
matches the frozen delivery fee and a valid provider quote is available; any
change becomes exception requiring operator resolution/refund. Never charge an
unapproved additional amount. The operational resolution is idempotently sent to
billing via authenticated internal API, not by overwriting its payment status.

Use C03's POST `/api/v1/billing/internal/payments/{payment_id}/resolution`
with `resolution=refund_required`, `resource_id=order_id`, and `reason`
(`quote_expired`, `order_cancelled`, `delivery_price_changed`, `duplicate_charge`).
Only fulfilment may flag its medication payment. Billing validates stored purpose,
resource, tenant and committed success before setting its operational resolution;
duplicate requests do not create another refund. Refund completion is fetched
from the authorized billing API and applied idempotently to fulfilment's order.

## Paid AND ready gate and delivery states

medicine_status progresses not_ready -> ready; readiness alone never submits.
Only a matching C05 medication payment (ID, order/tenant/patient, purpose,
accepted quote, exact SGD amount) sets payment_status succeeded. Compare stored
billing payment context as well as event data. Duplicate/out-of-order events
cannot toggle it back to unpaid or authorize a different order.

Submit exactly when payment_status=succeeded AND medicine_status=ready AND
order status=paid AND a current provider quote/unchanged paid fee is verified.
Payment first: awaiting_payment -> paid, wait for ready. Ready first: remain
awaiting_payment with ready, wait for payment. A durable transaction claims
paid -> submitting, creating a stable delivery operation key before provider I/O.
No simultaneous handler can submit twice. Persist uncertain outcomes and reconcile
by operation/provider reference before retry; do not treat timeout as failure.

Delivery requires `delivery_id`, `order_id`, `tenant_id`, `status`, `created_at`,
`updated_at`; normalized status values are `pending`, `submitted`, `picked_up`,
`delivered`, `cancelled`, `failed`, `unknown`. pending -> submitted on provider
acceptance, -> unknown on uncertain submission, -> failed on definite rejection.
submitted -> picked_up -> delivered; submitted may -> cancelled/failed;
picked_up may -> failed; unknown resolves to submitted/picked_up/delivered/failed
after verified reconciliation. A later verified delivered may jump over missed
intermediate statuses; terminal delivered never regresses on stale callbacks.
Provider status mapping/verification is D06; never trust an unsigned public callback.
Emit delivery_status_changed.v1 only for committed normalized changes.

Provider acceptance sets order dispatched; verified delivered sets delivered.
Definite submission/delivery failure sets exception, not delivered. Retrying a
definite failed submission requires an explicit audited action and revalidated
quote; it must reconcile the old operation first. Cancel before submitting closes
checkout/reservation; if already succeeded set refund_required and coordinate
manual full refund. Submitting/dispatched/delivered cancellation/refund is blocked
with 409 `delivery_already_started` until a separate reviewed provider resolution.
Refund completion may mark an exception order cancelled/refunded without erasing
delivery/audit history. Clinic readiness never implies payment or delivery success.

## Documents, errors and review

Document service generates one PDF per issued prescription through C05/P02.
GET `/api/v1/document/documents` (optional appointment_id; C01 pagination ordered
created_at, document_id ascending) returns metadata `document_id`, `tenant_id`,
`appointment_id`, `prescription_id`, `kind=prescription_pdf`, `status` (`pending`,
`ready`, `failed`), created_at/updated_at. GET `/documents/{document_id}/download`
returns 200 `{ "download_url": "https://...", "expires_at": "..." }` for ready
documents only; short-lived URL, private storage, browser-reachable host in local
mode. Own patient or assigned active doctor only; reads/downloads audited. S3 keys
and permanent public URLs are not exposed. Pending/failed -> 409 `document_not_ready`.

Unauthorized resources use C01 concealed 404. Authorized conflicts use 409
`prescription_not_issued`, `quote_expired`, `quote_superseded`, `already_paid`,
`delivery_already_started`; price/body/quantity errors use 422. Do not return
clinical text/address/provider payloads in errors. Quote/provider uncertainty uses
503 `delivery_pending_reconciliation`, preserving the operation for status queries.

[`examples/prescription-order-quote.json`](examples/prescription-order-quote.json)
provides linked prescription/order/quote/payment/delivery examples and both
gate arrival orders, with C05 IDs and total 2500 minor units. Synthetic item labels
and instructions are placeholders, not treatment advice or a real catalogue.
`order_after_payment` and `delivery_later` are different-time snapshots: the first
has no delivery yet; the later delivery demonstrates a normalized terminal state.
Consumer review with records/fulfilment/billing or prescription/order UI owner
must cover amount/quantity tampering, tenant mismatch, expiry equality, frozen
prices, payment/ready order, duplicate submissions and uncertain-provider recovery.
