# C03: booking, payments and expiry

Proposed domain contract under [C01](api-conventions.md), aligned with
[C05](events.md) and the [C02 access proposal](https://github.com/NorbertLoh/CS5224-Team-39/pull/36).
Consumer review is pending. S01-S06/B01-B05 implement these rules; fixtures do not
prove concurrency, webhook verification or payment integration.

## Resources and public scheduling API

Slots are fixed, non-overlapping half-open intervals `[starts_at, ends_at)` in
UTC, initially 30 minutes. Clinic display timezone is Asia/Singapore. Scheduling
owns slot capacity and appointments; one active reservation per slot. Public
slots require `slot_id`, `tenant_id`, `doctor_id`, `starts_at`, `ends_at`,
`availability` (`available` or `unavailable`) and `consultation_price` (indicative
C01 SGD Money). A quote is revalidated on hold; the browser cannot set a price.

Appointment responses require `appointment_id`, `tenant_id`, `patient_id`,
`doctor_id`, `slot_id`, `status`, `starts_at`, `ends_at`, `hold_expires_at`
(instant, null after confirmation), `consultation_price` (snapshot), `payment_id`
(UUID or null), `payment_resolution` (`none`, `awaiting_payment`, `confirmed`,
`refund_required`, `refunded`), `created_at`, `updated_at`. Expired/cancelled
appointments retain the former expiry for audit unless already confirmed.
Patient/doctor/tenant links are immutable. No clinical content in this resource.
Optional display snapshots `patient_name`, `doctor_name` and `clinic_name`
(string or null) are captured at booking from the patient's identity, the clinic's
active doctor directory and its booking profile. They are not refreshed after a rename.
They are null for appointments booked before scheduling migration `0007`, so
clients fall back to the identifiers.

| Route (prefix `/api/v1/scheduling`) | Body / result | Policy |
| --- | --- | --- |
| GET `/clinics/{tenant_id}/slots` | Required `from`, `to` UTC instants (at most 7 days), optional `doctor_id`; C01 paginated slots ordered starts_at, slot_id ascending | Public active clinic; no patient/reservation-owner details |
| POST `/clinics/{tenant_id}/slots` | `starts_at`, `ends_at`; slot, 201 | Active member doctor; server sets doctor_id to caller; active clinic |
| DELETE `/slots/{slot_id}` | 204 | Owning active doctor; 409 `slot_reserved` if an active reservation exists |
| POST `/appointments` | `tenant_id`, `slot_id`; appointment in held state, 201 | Patient role; server resolves patient_id, doctor and price |
| GET `/appointments` | Optional `tenant_id`, `status`, `from`, `to`, `period=upcoming\|past`; C01 pagination ordered starts_at, appointment_id ascending for upcoming/default, descending for past; period-bound cursors | C02 scoped patient/assigned doctor/clinic admin/platform metadata |
| GET `/appointments/{appointment_id}` | Appointment, 200 | C02 tenant/participant policy |
| POST `/appointments/{appointment_id}/cancel` | `{ "reason": "Patient requested cancellation" }`; appointment, 200 | Owning patient or active owning-clinic admin; no platform-only cancellation |

Dates must have a timezone, normalize to UTC, and start before end. Slot creation
requires a future 30-minute interval and rejects overlapping slots for the same
doctor, including across clinics (409 `slot_overlap`). Listing only reports a
snapshot: a displayed available slot is not reserved until POST succeeds.
No show is an explicit scheduling administrative action after ends_at;
consultation service requests in_progress/completed through authenticated internal
scheduling actions, not through a patient-editable PATCH. Internal action routes
are POST `/internal/appointments/{appointment_id}/start`, `/complete`, `/no-show`;
start/complete allow consultation service, no-show allows the scheduling operator.
All require validated resource context; public ingress excludes `/internal/*`.
Start is permitted from starts_at until ends_at; no-show only at/after ends_at.
V01/V02 additionally define admission windows; these actions do not grant video access.

## Hold expiry and legal booking transitions

POST /appointments atomically reserves an available slot and fixes
`hold_expires_at = min(server_now + 10 minutes, starts_at)`. Refuse a past slot.
The hold remains valid only while `server_now < hold_expires_at`; equality means
expired. A checkout does not extend the deadline. Redis TTL is an accelerator;
the persisted deadline, reservation constraint and transaction decide truth.

| From | To | Trigger and constraint |
| --- | --- | --- |
| held | pending_payment | Trusted checkout reservation accepted before expiry |
| held, pending_payment | expired | Deadline reached; release slot atomically |
| held, pending_payment | cancelled | Authorized cancellation; release reservation |
| pending_payment | confirmed | Verified successful payment matches tenant/appointment/currency/amount and capacity remains reserved |
| confirmed | in_progress | Validated consultation start |
| in_progress | completed | Validated consultation end |
| confirmed | no_show | Explicit administrative decision after ends_at, no consultation started |
| confirmed | cancelled | Authorized cancellation before starts_at; flag successful charge for manual refund |
| expired | confirmed | Late success only under the guarded recovery policy below |

Other transitions return 409 `invalid_appointment_transition`. Cancel is
idempotent for already-cancelled appointments. Completed/no_show appointments
remain historical and cannot be reopened. Failed payment attempts leave a
pending_payment appointment retryable until its original hold expires. Concurrent
checkout/cancel/expiry/payment handlers must use the same reservation transaction;
changing a Redis key alone must never confirm a booking.

### Late success (including cancellation race)

Use processing-time server clock, not event occurrence time or redirect time.
If a success arrives after expiry, first expire/release the old reservation in
the same transaction, then attempt to reserve the same slot again. Confirm only
if slot is unreserved, doctor still has active membership, clinic is active,
appointment is not cancelled, and starts_at is still future. Never take a slot
from a newer appointment. Retain a recovery audit entry.

If any condition fails, keep expired/cancelled state and set
`payment_resolution=refund_required`. The payment itself stays succeeded; record
the operational exception in billing. Display that no appointment was confirmed
and support must arrange a refund. Prototype refunds are a deliberate operator
action, not an unimplemented promise of automatic reconciliation. Refund success
changes resolution to refunded; a failed refund remains refund_required for retry.
Cancellation concurrent with success either confirms then cancels/refunds or
records success against cancelled state/refund_required; it must not reopen a
cancelled appointment. Duplicate successes produce no duplicate booking/refund.

## Billing and trusted price boundary

Payment requires `payment_id`, `tenant_id`, `patient_id`, `purpose`
(`consultation` or `medication_delivery`), `appointment_id` (UUID or null),
`order_id` (UUID or null), `quote_id` (UUID or null), `status`, `amount` (C01
Money), `commission_bps`, `commission_amount`, `clinic_amount`, `resolution`
(`none` or `refund_required`), `created_at`, `updated_at`. Exactly one purpose
link is present: consultation -> appointment, null order/quote;
medication_delivery -> order and quote, null appointment. Provider IDs and
webhook payloads are internal, never returned in ordinary patient responses.

RF08 adds `refund_availability` to public payments: `available`, `demo_payment`,
`unsupported_purpose`, `not_paid` or `unsupported_payment`. This is a payment-level
capability, not refund authority or confirmation of appointment eligibility;
current clinic membership and booking state are independently checked on POST.
Demo payments report `demo_payment` and cannot call the provider. Refund refusals
use `refund_demo_payment`, `refund_appointment_active` or `refund_not_available`
so clients do not mistake every HTTP 409 for an active appointment.

Billing obtains consultation price from scheduling's hold snapshot and commission
from tenant through authenticated APIs. It rejects inactive/expired/cancelled or
foreign appointments. C04 defines the trusted order/quote snapshot for medication.
Integer SGD amount snapshots never change when clinic/catalogue rates change.
For the prototype, commission applies to consultation and medication subtotal,
not delivery fee. `commission_amount = floor(commissionable_minor * commission_bps
/ 10000)`; `clinic_amount = amount - commission_amount`, both C01 Money in SGD.
For consultation commissionable_minor equals amount_minor. Clinic amount here is
the gross non-platform portion including delivery cost for medication payments;
it is not net Stripe payout or revenue. Provider fees/Connect settlement are X03/B01
implementation decisions, not inferred from this split. Totals must be safe integers.

| Billing route (prefix `/api/v1/billing`) | Body / response | Authorization |
| --- | --- | --- |
| POST `/consultation-checkouts` | `appointment_id`; `{payment, checkout_url, expires_at}`, 201; 200 on replay | Owning patient; checkout URL is provider-generated HTTPS, expiry <= hold deadline |
| GET `/payments/{payment_id}` | Payment, 200 | Owning patient, active tenant clinic admin, platform admin; no unrelated doctors |
| GET `/payments` | Optional `tenant_id`, `purpose`, `status`; C01 pagination ordered created_at, payment_id descending (newest first) | Same scoped policy; patient sees own charges only |
| POST `/payments/{payment_id}/refund` | `reason`; payment, 200 | Platform-admin operational action, full successful charge only; audit required |

Checkout requires `Idempotency-Key` (1-64 ASCII letters/digits/._-). Scope it to
authenticated subject and operation; retain at least 24 hours, including expiry.
Same key/body returns original result; different body returns 409
`idempotency_conflict`. Concurrent identical requests create one attempt. Allow
one pending/succeeded payment per linked appointment; a new key while pending
returns the existing checkout, while succeeded returns 409 `already_paid`.
Failed attempts can be retried under a new key before expiry. Do not create a
new charge after uncertain provider timeout; reconcile the original operation
using the persisted provider idempotency key. Provider return/cancel URLs come
from configured allowlists, never arbitrary request URLs.

Before any provider checkout creation, billing calls service-only POST
`/api/v1/scheduling/internal/appointments/{appointment_id}/checkout-reservation`
with `payment_id`; scheduling atomically verifies ownership/context, hold validity
and held/pending_payment state, records that payment_id, moves to pending_payment
and returns appointment plus trusted price. Repeating the same payment_id is safe;
a different ID is allowed only after billing proves the prior attempt failed.
Both APIs require authenticated allowlisted service callers. An expired reservation
cannot be renewed by checkout retries. A provider failure is recorded as failed
payment; appointment remains pending_payment until retry/expiry/cancel.

## Payment transitions and events

| From | To | Authority |
| --- | --- | --- |
| pending | succeeded | Verified provider callback or authenticated reconciliation; amount/currency/purpose/resource match stored snapshot |
| pending | failed | Verified provider terminal failure; redirect/cancel page alone is insufficient |
| failed | succeeded | Verified late provider success for that same attempt; apply scheduling/fulfilment recovery policy |
| succeeded | refund_pending | Audited full-refund operation, idempotent persisted refund key |
| refund_pending | refunded | Verified refund completion |
| refund_pending | refund_failed | Verified terminal refund failure |
| refund_failed | refund_pending | Audited retry using reconciled provider outcome |

Never regress succeeded on a delayed failure; never issue another charge because
an old attempt failed locally. Refunds do not rewrite the original amount.
Provider event ID plus inbox/outbox transaction prevent duplicate effects.
A refund cannot undo a delivered order; C04 restricts medication refund actions.

Billing commits payment truth and the relevant C05 success event together.
Scheduling confirms only after validating the event against the bound payment
and trusted appointment amount; if it confirms, it publishes appointment_confirmed.
Billing marks resolution/refund requirement through authenticated idempotent
internal coordination (implementation in S06), never a cross-service table write.
POST `/api/v1/billing/internal/payments/{payment_id}/resolution` requires
`resolution=refund_required`, `resource_id` and `reason`. Allow scheduling for
consultation payments (`slot_reallocated`, `appointment_cancelled`,
`appointment_unavailable`, `duplicate_charge`) and fulfilment for medication
payments (C04 reasons). Validate stored succeeded payment, tenant, purpose and
linked appointment/order before applying; return payment, 200 on repeat without
duplicate refund. Public ingress excludes this endpoint. Operator refund completion
is read from authorized billing APIs by the resource owner and applied idempotently
to appointment/order resolution. This flag requests review; it does not itself call
the provider refund API. During refund_pending/refund_failed the flag is retained;
on refunded it clears to none and the resource owner's resolution becomes refunded.
Resource retrieval and amount verification remain necessary even for trusted events.
For an earlier failed attempt's late success, scheduling may bind that successful
payment only if no different payment already confirmed the appointment. An extra
successful charge is flagged for refund; never silently switch confirmed payment IDs.

## Fixtures, errors and review

[`examples/booking-payment.json`](examples/booking-payment.json) demonstrates a
confirmed appointment/payment, exact expiry boundary, late recovery and a
reallocated-slot refund exception. IDs/amounts match C05 consultation examples;
those six transport fixtures are independent committed facts, not a chronological
live patient history.

Inaccessible IDs -> C01 404 before state checks. Own conflicts use 409
`slot_unavailable`, `hold_expired`, `already_paid`, `invalid_appointment_transition`
or `clinic_not_active`. Invalid money/body/time/filter -> 422; provider uncertain
outcome -> 503 `payment_pending_reconciliation` with a stable payment ID retrievable
by GET (do not auto-retry mutation with a new key).

Consumer review: scheduling/billing or booking/checkout UI owner should check
deadline equality, duplicate success, same-slot race, cancellation race, late
payment after reallocation, amount mismatch and historical commission stability.
Manual refund-required messaging is part of U09; no real flow is verified here.
