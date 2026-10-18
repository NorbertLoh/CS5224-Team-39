# B07 live billing integration

Issue #190 / PR #191 connects the existing B02/B05 APIs to booking, patient
payment status and clinic payment history. No billing schema or service contract
changes are required.

## Start and configure

Use the existing identity, tenant and scheduling setup. Start billing on port
8009 after applying migrations through `0005`; follow
[checkout configuration](../services/billing/CHECKOUT.md),
[payment queries](../services/billing/PAYMENT_QUERIES.md) and
[payment workers](../services/billing/PAYMENT_PROCESSING.md). Configure the scoped
service credentials, Stripe test destination map, signing secret and independent
`SERVICE_CURSOR_SECRET`. Keep the expiry worker running. Processing, publication
and scheduling's consumer must run for payment success to confirm a booking.

The Vite development proxy forwards `/api/v1/billing` to
`BILLING_API_TARGET` (default `http://127.0.0.1:8009`) and strips that prefix.
Internal billing routes are blocked, including percent-encoded internal paths.
Restart Vite after changing its target. Deployed ingress needs the same rewrite
and internal-route exclusion; Vite preview is not an API proxy.
`VITE_USE_AWS=true` continues using the configured deployed API base.

Use one browser origin consistently, including the hostname. Set both billing
`SERVICE_CHECKOUT_SUCCESS_URL` and `SERVICE_CHECKOUT_CANCEL_URL` to
`http://localhost:5173/patient/checkout` for that local origin (HTTPS in deployment).
The older service defaults `/payments/return` and `/appointments` also resolve to
the protected live payment page. Return URLs are server configuration; the browser
sends only appointment ID and Idempotency-Key when creating checkout.

## Patient flow

Reserve a slot, follow **Continue to payment**, then **Continue to secure checkout**.
The payment page reads the authenticated appointment and its current linked
payment, checking patient, tenant, purpose and payment/appointment references.
It displays server amounts and the original hold deadline drives payment eligibility.
It refreshes every five seconds, on window focus and on manual request.
A return or query-string flag cannot establish payment success. Success requires
billing success and scheduling confirmation. Refund-required and uncertain outcomes
retain support/status guidance; this feature does not perform refunds.

Before checkout creation, store a key scoped to the signed-in subject and booking
in sessionStorage. Retain it through transport errors, reloads and pending reads.
An authoritative failed-attempt read permits one new key for that failed attempt;
a subsequent pending read retains that key. Mutations have no automatic retries.
Every explicit attempt refreshes appointment/payment status before creating or
resuming checkout. The original server deadline and backend reservation rules
remain authoritative. Only an unexpired HTTPS `checkout.stripe.com` URL can be opened.

The last checkout appointment is saved per subject in the same browser tab before
sending the create request, so provider returns need no provider identifiers in
the URL. If tab storage is unavailable or the return occurs on another device,
open **Appointments**, select the booking, then **Payment status and checkout**.
Explicit `appointment_id` navigation still goes through authenticated ownership
checks. An unavailable reference shows recovery guidance, without fixture data.

## Clinic flow

The managed clinic **Payments** link opens live tenant-scoped history. Purpose
filters apply to both history and totals; status filters apply only to history.
Load more follows the opaque server cursor. Summary amounts come from the
independent server totals endpoint, never a partial page or a browser calculation.
Details use each payment's immutable snapshots. Clinic names come from tenant API
with the selected clinic ID as the fallback label. Refresh and window focus reload
server data. Loading or failed reads do not substitute fixture rows or zero totals.
Query caches are partitioned by token, clinic and filters; normal sign-out clears
the shared cache. Billing remains responsible for fresh authorization per request.

The separately labelled `/patient/checkout-preview` remains a synthetic design
preview. Fixture modules support its examples and regression tests, and are not
used by live payment reads.

## Verification and limits

`npm test`, `npm run lint` and `npm run build` from `apps/web` passed locally.
The 102 frontend tests include request authorization/filter/cursor checks, stable
checkout keys after uncertainty and failure, exact expiry, linked payment validation,
confirmation/refund states, redirect host checks, live clinic rendering and loading.
An actual loopback Vite HTTP proxy test verifies prefix removal, header/body
forwarding and internal-route rejection against a synthetic HTTP upstream.

These checks do not establish actual billing-service/Stripe webhook processing,
real booking confirmation, browser interaction or AWS operation. The full real
clinic -> booking -> Stripe payment -> confirmed appointment journey remains I01;
provider and scheduling/refund reconciliation limits from B02/B04 remain applicable.
Keep B07 In progress until its PR is merged and completion criteria are accepted.
