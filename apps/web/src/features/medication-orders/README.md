# Medication order preview (U15)

Sign in as a patient and open **Preview medication order and delivery payment
(synthetic data)** from the patient dashboard, or visit
`/patient/medication-order-preview`. The existing role guard applies. No new
environment variables, API calls, checkout redirect or browser storage are used.

The issued prescription, fixed quantities, medication prices and SGD 20 + SGD 5
delivery = SGD 25 total come from the linked C04 contract example. Address input
is validated as a structured Singapore destination, held in component memory,
and discarded on navigation/reload. Use synthetic addresses. Changing an address
invalidates its unaccepted quote; the preview fee stays fixed at SGD 5.

Create the demo order, request a quote, then preview payment. Quotes expire ten
minutes after the demo request; the historical clock starts at 12 October 2026,
11:00 SGT and advances in real time. **Preview controls** can advance directly to
the deadline, fail the next quote, or choose the next payment status response.
Selecting a response does not itself change payment; click **Check demo payment
status**. Pending, cancelled return, unavailable status and payment awaiting order
confirmation block new quotes/payments, including after expiry. Only verified
failure allows retry before expiry. Payment confirmation does not imply dispatch.
The late-payment example requires manual refund review.

Order scenarios also expose loading, unavailable/retry, empty, draft and voided
prescriptions. Switching scenarios resets the example. The preview never consumes
a live prescription or changes live order/payment state. U16 owns readiness and
tracking views; D07 owns real fulfilment APIs, authoritative quote/pricing, checkout
reservation, Stripe redirect and verified payment/order refresh. This feature
does not complete those integration tasks.

Verification: `npm test`, `npm run lint` and `npm run build` in `apps/web`.
Focused tests cover C04 quantities/prices, route access, address invalidation,
expiry equality, blocked duplicate attempts, verified retry and refund messaging.

Local verification on 19 October 2026 passed all 123 frontend tests, lint,
TypeScript and the production build. After the demo-clock correction, all nine
focused tests, lint/build and the browser journey passed again. Chromium checks
at 1280 × 1000 and 390 × 844 used a synthetic session and intercepted identity
response on the actual protected route. They exercised address invalidation,
quote expiry/refresh, pending/cancelled/unknown/failed payment, retry,
confirmation, manual refund review, quote failure/recovery, all order scenarios,
and denial of a nonpatient identity. Neither viewport overflowed horizontally;
there were no page errors or write requests. These checks establish fixture UI
behaviour, not real authentication, fulfilment or payment integration.
