# I01 local journey: clinic approval -> booking -> Stripe payment -> confirmed

Status: verified locally on 20 October 2026 with real services, a real Stripe
test-mode payment and no fixtures. AWS operation is out of scope (W-tasks).

## Stack

Follow the existing setup guides; this run used them unchanged:

- Compose dependencies and Floci bootstrap: [local development](local-development.md).
- Identity/tenant: [clinic backend](clinic-backend.md), including `dev/clinic_local.py`.
- Scheduling: [API setup](../services/scheduling/docs/api.md) and
  [payment workers](../services/scheduling/docs/payments.md).
- Billing: [checkout](../services/billing/CHECKOUT.md),
  [webhooks](../services/billing/WEBHOOKS.md) and
  [payment processing](../services/billing/PAYMENT_PROCESSING.md).
- Frontend and Stripe forwarding: [B07 live billing](B07-live-billing.md).

All four service schemas live in the persistent `telelink-clinic-postgres`
container (port 55411). Scheduling uses Compose Redis (`redis://127.0.0.1:6379/0`).
Each schema is provisioned with its service's `scripts/create-local-schema.sql`
and migrated to head (identity `0002`, tenant `0003`, scheduling `0007`, billing `0005`).

Thirteen processes run alongside Compose:

| Process | Command (from the service directory) |
| --- | --- |
| identity API (8001) | `uvicorn app.main:create_app --factory --port 8001` |
| tenant API (8002) | `uvicorn app.main:create_app --factory --port 8002` |
| scheduling API (8003) | `python -m app` |
| scheduling hold expiry | `python -m app.expire_holds` |
| scheduling payment consumer | `python -m app.payment_worker` |
| scheduling confirmation publisher | `python -m app.payment_worker --publish` |
| scheduling refund-flag resolver | `python -m app.payment_worker --resolve` |
| billing API (8009) | `python -m app` |
| billing checkout expiry | `python -m app.expire_checkouts` |
| billing payment processor | `python -m app.payment_worker` |
| billing success publisher | `python -m app.payment_worker --publish` |
| frontend (5173) | `npm run dev` in `apps/web` |
| Stripe forwarder | `stripe listen --events ... --forward-to http://127.0.0.1:8009/webhooks/stripe` (B07) |

Configuration notes beyond the existing guides:

- Shared service keys must match pairwise: tenant `SERVICE_SCHEDULING_SECRET` =
  scheduling `SERVICE_SCHEDULING_SECRET`; scheduling `SERVICE_BILLING_SECRET` =
  billing `SERVICE_SCHEDULING_SECRET`; billing `SERVICE_TENANT_SECRET` = tenant
  `SERVICE_BILLING_SECRET`. All other keys and cursor secrets are distinct.
- Workers that use Floci EventBridge/SQS need `AWS_ACCESS_KEY_ID=test` and
  `AWS_SECRET_ACCESS_KEY=test` in the **process environment**. Values in a service
  `.env` are not read by boto3 and the scheduling consumer exits with
  `NoCredentialsError`.
- Billing readiness requires `SERVICE_FULFILMENT_URL`/`SERVICE_FULFILMENT_SECRET`
  and a non-empty `SERVICE_STRIPE_DESTINATIONS`, even though this journey does not
  use fulfilment. After approving the clinic, map its tenant ID to the Stripe test
  connected account and restart the billing API.
- Billing `SERVICE_STRIPE_SECRET_KEY` is an `sk_test_` key; the forwarder reads the
  same key from `STRIPE_API_KEY`. Set `SERVICE_STRIPE_WEBHOOK_SECRET` from
  `stripe listen --print-secret` before starting the billing API.
- Return URLs: `SERVICE_CHECKOUT_SUCCESS_URL` and `SERVICE_CHECKOUT_CANCEL_URL`
  are both `http://localhost:5173/patient/checkout`.

## Journey

The frontend has no clinic application form, so the pending clinic is submitted
through the real tenant API. Every later step uses the browser as the
relevant Floci demo account.

1. **Submit (API):** `services/identity/.venv/Scripts/python.exe tests/e2e/check_i01_journey.py submit-clinic`
   created `I01 Journey Clinic` (`i01-1bf0ef60`, SGD 25.00) in `pending_review`, owned by `clinic@example.test`.
2. **Approve (platform admin):** *Platform clinics -> Manage clinic*: commission set
   to 10%, **Approve clinic**; status changed to Active.
3. **Staff (clinic admin):** *Staff management*: assigned `doctor@example.test` the Doctor role.
4. **Availability (doctor):** clinic timetable: selected 21 Oct 10:00 SGT and **Add availability**.
5. **Book (patient):** storefront -> *Book a consultation* -> 21 Oct 10:00 ->
   *Continue to checkout*. The appointment `c01e9347-6a69-4a0e-9c34-19436bb9144c` was held
   with a server deadline of 17:42:44 SGT.
6. **Pay (patient):** *Continue to payment* -> *Continue to secure checkout* -> Stripe
   hosted Checkout (test mode) with card `4242 4242 4242 4242` -> returned to
   `/patient/checkout`, which displayed **Appointment confirmed**, SGD 25.00 and
   payment `2387644f-1bd4-4703-b1b4-89ed595308a5`.

The browser steps were driven by a local Playwright script using the project's
`@playwright/test` dependency, against the real UI. The script is not committed
because broad browser automation is deferred (see [tests/e2e](../tests/e2e/README.md)).

## Evidence

Event chain at 17:33 SGT, about 4 seconds from payment to confirmation, well
before the hold deadline:

| Hop | Observed |
| --- | --- |
| Stripe -> CLI -> billing | `payment_intent.succeeded` and `checkout.session.completed` forwarded; receiver returned `[200]` for both |
| billing receipts | both `stripe_webhook_events` rows `processed`, 0 retries |
| billing processor | re-read the Checkout Session and PaymentIntent from Stripe, then marked the payment succeeded |
| billing outbox -> Floci EventBridge | `consultation_payment_succeeded.v1` published, 0 retries |
| scheduling consumer | inbox recorded the event; authoritative payment read from billing `/internal/payments/{id}` |
| scheduling outbox | `appointment_confirmed.v1` published, 0 retries |
| appointment | `confirmed`, payment resolution `confirmed`, hold deadline cleared |

The clinic admin *Payments* page showed one succeeded consultation payment:
total SGD 25.00, platform commission SGD 2.50 (10%), clinic gross SGD 22.50.

The re-runnable backend check passed all seven assertions:

```text
> services/identity/.venv/Scripts/python.exe tests/e2e/check_i01_journey.py verify c01e9347-6a69-4a0e-9c34-19436bb9144c
PASS  clinic approved and active
PASS  appointment confirmed
PASS  appointment payment resolution confirmed
PASS  payment succeeded
PASS  payment is the consultation for this appointment
PASS  same patient and clinic
PASS  amount matches booked price
clinic=i01-1bf0ef60 appointment=c01e9347-6a69-4a0e-9c34-19436bb9144c payment=2387644f-1bd4-4703-b1b4-89ed595308a5 amount=SGD 25.00
```

`verify` exits non-zero if any check fails. It only reads data, through the patient
and platform demo accounts.

## Findings and limits

- Scheduling `/health/ready` compares the schema revision with `0005`, but head is
  `0006`, so readiness returns 503 on a fully migrated database
  (`services/scheduling/app/main.py`). The API and workers operate normally.
  This is a suggested follow-up fix.
- Appointment views showed raw patient/doctor/clinic UUIDs. Fixed in this PR:
  scheduling now captures the patient, doctor and clinic names at booking (migration
  `0007`, optional C03 fields) and the frontend shows them. Older appointments still
  show identifiers. Verified with a second paid booking (`83553bba-…`), whose detail
  view showed the names for the patient, doctor and clinic admin.
- The clinic selectors on the clinic admin appointments page and the doctor
  availability page listed clinic UUIDs. They now show clinic names: tenant clinic
  reads for clinic administrators and the public directory for doctors, falling
  back to the ID if a name is unavailable.
- There is no clinic application UI; clinic onboarding is API-only (consistent
  with the plan's seeded clinics and manual review).
- Not covered: AWS deployment, refunds/late-payment recovery in the browser, and
  the Stripe Connect payout itself (the destination account was configured but
  transfers were not inspected).
