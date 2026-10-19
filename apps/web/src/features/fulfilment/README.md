# U16 readiness and tracking previews

Patient: sign in as `patient@example.test` and follow **Preview medication
delivery tracking (synthetic data)** from `/patient`, or open
`/patient/delivery-tracking-preview`.

Clinic: sign in as `clinic@example.test`, open `/clinic-admin`, and choose
**Preview readiness and tracking** from an actively managed clinic. The route is
`/clinic-admin/clinics/<tenant UUID>/fulfilment-preview`. Active owning-clinic
administration is required; a patient, doctor, revoked/other-clinic administrator
or platform role alone cannot open the clinic readiness preview. Both local
accounts use the existing `LocalDemo123!` password. Use port 5173 for the existing
local Cognito callbacks; start local auth/identity services as documented in
`docs/clinic-backend.md`.

No new configuration, backend routes, network writes, storage or migrations are
introduced. The existing shell verifies access through the identity API. Orders
are synthetic C04 projections: the patient view uses the demo patient; the clinic
fixture set is bound to the selected clinic ID. They are not the signed-in user's
live orders. Operational fields exclude notes, instructions, doctor identifiers
and full delivery addresses. Separate components handle example controls, order
selection/detail, medicine readiness and delivery tracking.

## Walkthrough

1. In **Active orders**, select demo order 001 (paid, not ready). Mark medicine
   ready in the clinic view. Its payment/order/quote/delivery fields stay unchanged,
   and no courier is confirmed. The action disables once ready.
2. Select demo order 002 (unpaid, not ready), then mark ready. The order remains
   unpaid and delivery waits for confirmed payment. Demo order 003 starts paid
   and ready, with no delivery yet.
3. Check **Simulate readiness action error** before marking a fresh example ready.
   The failure leaves readiness unchanged; clear it and retry the same action.
4. Switch **Tracking example** through pending submission, courier acceptance,
   pickup, completion, cancellation, failure and unknown outcome. These are
   independent snapshots, not a simulated sequence or reconstructed event history.
   Unknown outcomes require reconciliation rather than another delivery attempt.
5. Expired/changed quotes and refund review explain manual resolution without
   promising extra charges, an automatic refund or automatic resubmission.
6. Check loading, empty and unavailable states. Unavailable hides all order/detail
   content; **Retry demo orders** restores fresh active examples. **Refresh demo
   status** checks the current snapshot without advancing delivery or resetting
   readiness. Switching examples, clinics or reloading resets local changes.

The patient screen is read-only. These independent patient/clinic previews do not
share state between tabs or persist readiness. D07 owns live orders, service
authorization, readiness writes and verified provider/payment refresh. U15 owns
the separate fixture order/quote/payment screen; neither preview completes the
real medication checkout or delivery journey.

Order borders show urgency: red for problems/manual review (including unknown or
cancelled delivery), amber for payment/preparation waits, blue for progress, green
for verified delivery completion and grey for refunded orders. A matching text
label keeps the meaning available without colour. Selection adds a separate ring
and preserves the status border.

## Verification

From `apps/web`: `npm test`, `npm run lint`, `npm run build` and Prettier checks.
The eight focused tests cover role/clinic scoping, one-way readiness/retries,
inactive/unissued orders, fixed C04 operational projections, independent delivery
truth, manual resolution and loading/empty/error examples.

Local checks on 19 October 2026 passed all 131 frontend tests, lint, TypeScript
and production build. Isolated Chromium journeys at 1280 x 1000 and 390 x 844
used a synthetic browser session and intercepted identity on the actual protected
routes. Both roles, ready-first/paid-first cases, failed-action recovery, every
tracking example, unavailable/retry, context/role denial and refresh passed, with
no runtime errors, horizontal overflow or write requests. This verifies fixture
UI behaviour; real authentication, fulfilment and provider integration are not
established by these browser fixtures.
