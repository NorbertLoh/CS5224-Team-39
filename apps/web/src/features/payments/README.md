# U10 clinic payment preview

Sign in as an active clinic administrator, open **Clinic administration**, then
choose **Payments preview** on the managed clinic card. The route is
`/clinic-admin/clinics/<tenant UUID>/payments`. The existing application shell
checks current identity/membership and provides role navigation. Platform admins
retain the existing tenant-management policy. The page also links back to the
clinic workspace, profile and staff. No configuration or dependencies are added.

This is synthetic data, not billing integration. `fixtures.ts` reuses
`dev/fixtures/telelink.json` and adds three independent synthetic refund-state
examples. Unknown clinic IDs show zero totals and no unrelated payment rows;
route access is checked by the shell before mounting. Fixture clinic names are
explicitly sample names and are not fetched from tenant APIs.

The payment-purpose filter changes both the summary and history. The history
status filter changes only the list, matching B05's independent totals endpoint.
Expandable rows show immutable commission/rate and clinic-gross snapshots,
appointment/order/payment references and Singapore timestamps. No patient names,
clinical content, provider identifiers or webhook bodies are shown. Refund review
is guidance only; there are no payment/refund/rate mutations.

Summary rules match `services/billing/PAYMENT_QUERIES.md`: count only succeeded
payments with resolution `none`; exclude pending, failed, refund-required,
refund-processing, refund-failed and refunded rows. Sum stored minor-unit amounts
instead of applying today's commission rate. Delivery fees are excluded from
commission; the clinic gross portion includes delivery costs and is before
provider fees. These operational current-state totals are not net payouts,
accounting revenue or a refund ledger. Invalid/unsafe non-SGD totals are rejected.

B07 must replace fixture lists/totals with authenticated, tenant-scoped billing
API reads, real tenant names, pagination, loading/error/retry handling and fresh
access checks. Preserve the independent summary/filter semantics and use the
server totals endpoint rather than summing a partial paginated list. This task
does not establish live Stripe, scheduling/refund or AWS integration.

Verification: 94 frontend tests passed, including six U10 checks covering access,
revocation, tenant filtering, delivery commission snapshots, refund exclusions,
unsafe amounts, navigation, details and empty results. ESLint, TypeScript and
production build passed. The local standalone fixture viewer serves the page,
component modules and generated Tailwind utilities over HTTP. Browser interaction,
visual/mobile and AWS verification remain unperformed.
