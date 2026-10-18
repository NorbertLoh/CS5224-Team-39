# U09 checkout preview

Sign in as a patient and follow **Preview checkout outcomes (synthetic data)**
from `/patient`, or open `/patient/checkout-preview` directly. The normal
identity gate protects this route. No new environment variables or dependencies
are required; use the existing local authentication/backend setup.

The scenario selector covers provider return, pending, failed, checkout cancelled,
confirmed, paid but awaiting scheduling, expired hold, recovered late payment,
manual refund required, refund processing/completed, unavailable status and
missing reference. **Check fixture status** reads the selected static snapshot;
**Preview payment retry** returns a failed attempt to the return screen without
calling a provider. Select another scenario to change the simulated outcome.

All data is synthetic. Amount, appointment/payment references and consultation
time come from `contracts/examples/booking-payment.json`. The server clock is
frozen at 12 October 2026 11:00 SGT for repeatable historical scenarios; the hold
is valid strictly before its original deadline. No live booking is modified and
no payment is taken. URL query parameters are never used to determine status.

`status.ts` separates payment truth from scheduling confirmation: a successful
payment alone is insufficient for a confirmed booking. Uncertain/pending/paid
outcomes offer no payment retry. Unrecoverable late payments show manual clinic
support/refund guidance without promising an automatic refund. The cancel return
alone does not mark payment failed or cancel the appointment.

B07 must replace fixture reads with authenticated billing and scheduling data,
validate reference ownership/context, add real refresh/polling and checkout
handoff/idempotency, and use server deadlines. This preview does not establish
real billing, Stripe, cross-service or AWS integration.

Verification: 88 frontend tests cover route access, default return messaging,
exact expiry boundaries, delayed confirmation, late recovery, refund outcomes,
retry restrictions and screen content. ESLint and production build are checked
before PR review. Browser interaction/visual and AWS checks remain unverified.
