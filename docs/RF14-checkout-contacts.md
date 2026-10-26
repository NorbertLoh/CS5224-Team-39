# RF14 medicine checkout contact details

Medicine checkout asks the patient to confirm recipient name, contact number,
delivery address and six-digit Singapore postal code before calculating the total.
Fields initially use the order's confirmed details, or the patient Profile when
the order has no saved details. Profile refetches do not replace local edits.
Editing a field disables payment until the patient confirms a new quote.

**Save to my profile** is unchecked by default. Without it, edits apply only to
the order. When checked, the existing authenticated Profile API saves the entered
details before quotation. A failed Profile save stops quotation and explains how
to retry or continue without saving; a successful Profile save is reported even
if quotation subsequently fails. This is two separate service operations, not an
atomic cross-service transaction. Details are never stored in browser storage;
only an idempotency fingerprint and key are retained there.

## Service behavior

New `POST /orders/{order_id}/quotes` requests require `recipient.name` and
`recipient.phone_number` alongside the existing `destination`. Names and addresses
must be nonblank plain text. Phone numbers accept local eight-digit Singapore
numbers and normalize them to `+65...`; the first digit must be 6, 8 or 9.
The existing quote destination JSON holds the normalized recipient contact, so no
migration or new environment settings are needed. Contact changes affect the
idempotency fingerprint and require a new key/quote; old quote snapshots remain
unchanged. The quote is bound to the order and becomes immutable when accepted
for payment.

Shared quote responses add only `contact_confirmed`; they continue to omit all
addresses and recipient details. Authenticated
`GET /orders/{order_id}/delivery-details` returns the current quote's destination
and recipient to the owning patient or an active owning-clinic administrator,
with `Cache-Control: no-store`. Foreign/revoked clinic memberships, doctor and
platform-only roles do not grant access; other patients cannot read it.
Clinic order details display the booking-time patient name from the authorized
scheduling appointment separately from the saved delivery recipient, phone and
address/postcode. The appointment must match the order's clinic and patient.
Missing legacy contacts show Not confirmed, without substituting a current Profile.
Billing reservation responses and application events carry no new private data.

First checkout of an old unpaid quote requires confirmed contact. The API returns
`delivery_contact_required` until the patient requests a new quote. Existing
payment replays and paid/prepared delivery requests retain their behavior. New
courier preparation uses the saved quote contact, so editing the Profile later
cannot change the recipient. Legacy deliveries without a quote contact continue
to use the previous trusted Profile/directory lookup. Malformed saved contacts
fail closed rather than falling back to a different recipient.

## Verification and setup

Clinic-details refinement: all 378 fulfilment tests and frontend lint/typecheck/
build passed. Read-only shared-HTTPS checks verified owning-clinic access to the
matching appointment patient name and saved order contact/address, plus doctor
and platform-only denial. Browser automation was disabled in Work settings, so
the clinic-details visual layout was not checked. No order/Profile mutations.

- All 378 fulfilment tests passed in a separate RF14 disposable PostgreSQL database.
  Checks cover recipient normalization/validation, private patient/owning-clinic readback,
  replay/conflict behavior, quote immutability, legacy first-payment blocking,
  existing-payment replay and courier use of saved contact after Profile changes.
- Frontend lint/typecheck/production build and backend Ruff/format passed.
- Live shared-HTTPS browser checks on an unpaid synthetic demo order verified
  saved-Profile prefill, invalid-phone blocking, editable order-only contact,
  unchanged Profile when unchecked, Profile persistence when checked, field
  retention after quotation and disabled payment while edits await confirmation.
  Real sandbox quotation returned SGD 7.80 delivery and SGD 10.05 total. The
  synthetic Profile was backed up and restored; the unpaid order was re-quoted
  with the original Profile contact after the snapshot retention check. No payment or courier delivery
  was submitted.

Rebuild web and fulfilment, then recreate web, fulfilment and delivery-worker.
Retain `.local/compose/tailscale.yaml` for the current shared-HTTPS deployment.
No schema migration or configuration keys are added. AWS and a new paid-to-courier
journey for this contact snapshot remain unverified.

PR #287 merged into main on 26 October 2026 after signup dependency PR #285
and all final checks passed; issue #286 closed. The backlog records both tasks complete.
