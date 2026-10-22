# I03: issued prescription to one sandbox delivery

Verified on 22 October 2026 (Singapore time) using actual local service APIs,
Stripe test Checkout and Lalamove's SG sandbox. No business rows, timestamps or
provider success states were fabricated. No application behavior changed.

## Setup and rerun

Use the [I02 host setup](I02-local-journey.md) and
[D07 fulfilment configuration](D07-live-fulfilment.md). Keep the existing local
PostgreSQL database on `55411`, Redis, Floci and independently migrated schemas.
The consultation, records, fulfilment and document heads are `0002`, `0005`,
`0005` and `0003`; billing is `0005` and scheduling is `0007`.

Configure distinct peer secrets, actual sandbox credentials, trusted clinic and
postcode coordinates, and private synthetic courier contacts using those guides.
Remove `SERVICE_DISPENSING_FIXTURE_PATH` entirely when using real records; an empty
value is parsed as a path and conflicts with `SERVICE_RECORDS_URL`.
For Python 3.12+ editable installation without bundled setuptools, use
`pip install --no-deps -e packages/python_common` from the repository root.

Start the I02 APIs and publishing/consuming workers. Also run fulfilment's payment
consumer and delivery outbox publisher. Keep the official Stripe CLI forwarder,
billing processor/publisher and scheduling consumer/publisher running. Use
`python -m app.delivery_worker --once` from `services/fulfilment` at the gate checks
below; this run deliberately controlled submission with one-shot worker calls.
Tracking is `python -m app.tracking_worker --once`.
Local AWS clients need exported dummy credentials and the Floci endpoint.

1. Book a future slot as the synthetic patient and complete its real consultation
   Stripe test Checkout. Wait for the actual start time, then use the assigned
   doctor's consultation/records APIs to start, save a note, draft and issue a
   catalogue-backed prescription, and complete consultation without an MC.
2. Open the prescription's medication order as that patient. Request a real
   sandbox quote, then create and complete a separate medication Stripe Checkout.
   Confirm the signed webhook/outbox/SQS path makes the order paid.
3. While medicine is not ready, run the delivery worker: no delivery is claimed.
   Mark medicine ready as the owning clinic, run the worker, then repeat it:
   exactly one provider submission is retained.
4. Verify the linked resources with the read-only checker below. Inspect the
   patient medication page for payment, readiness, total and delivery status.
5. Cancel only that synthetic sandbox order after checking its provider metadata
   matches the local delivery/operation IDs. Use the existing signed sandbox
   adapter; the X05 CLI intentionally rejects orders without its own spike tag.
   Run tracking once to persist the provider's cancellation. Preserve audit rows.

From the repository root, with fulfilment's installed dependencies:

```powershell
services/fulfilment/.venv/Scripts/python.exe tests/e2e/check_i03_journey.py <appointment-id> <order-id> <consultation-payment-id>
```

Add `--config-root <configured-checkout>` for a separate source checkout. SQL uses
the fulfilment role and enforces read-only transactions. The checker neither
creates nor repairs business state. It also accepts a verified cancelled delivery
after cleanup; that state does not mean delivered or refunded.

## Observed evidence

| Boundary | Result |
| --- | --- |
| Consultation payment | SGD 25.00; genuine Stripe test Checkout; booking confirmed |
| Doctor issuance | Actual start time respected; note saved, prescription issued, consultation completed |
| Private PDF | Records event published; document worker generated a ready prescription PDF and published its event |
| Medication quote/payment | SGD 2.00 medication + SGD 7.80 delivery = SGD 9.80; distinct succeeded payment with order/quote linkage |
| Callback processing | Two `payment_intent.succeeded` and two `checkout.session.completed` receipts processed; both payment-success outbox events published |
| Paid, not ready | Real worker: `claimed=0`, `checked=0`; zero delivery rows |
| Paid and ready | Real provider quotation and order POST returned 201; worker `claimed=1`, `checked=1`, `errors=0` |
| Repeated worker | `claimed=0`, `checked=0`; one persisted delivery/provider reference |
| Patient frontend | Payment confirmed, medicine ready, SGD 9.80, dispatched/courier accepted |
| Cleanup | Matching sandbox order cancelled; authenticated provider GET confirmed `CANCELED`; tracking persisted cancellation |

Appointment `502824f7-7eb1-4282-bee5-4aa963dd9e1c`, prescription
`010322dd-039c-406b-b5d1-3e118834b02b`, order
`05a21d8b-bef9-4b37-a274-e938bfe6acb6`, delivery
`fa577d52-1d46-458b-be4b-6ecc7cb5ce8b`.
Consultation payment `daf96f94-fa4c-4f15-a788-28ab66fbff9f`; medication payment
`ce8c60a3-0da2-4c89-ae8f-403df25d84d1`.
Screenshots and private runtime configuration remain local under `.local/i03`.

All eight read-only checks passed. Substituting the medication payment ID for the
consultation payment was rejected. Seven existing disposable PostgreSQL gate,
repeated-poll and concurrent-worker checks passed, including readiness without
payment; those unit checks use explicit provider/billing fixtures. The actual
journey above used real HTTP providers and no response mocks.

This run did not repeat I02's video call, issue an MC, perform physical pickup or
delivery, send real email, deploy AWS or execute a refund. Cancellation preserves
the succeeded test payment and shows an exception in tracking. Notification
journey evidence is separately tracked by I04.
