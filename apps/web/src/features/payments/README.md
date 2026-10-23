# Clinic payments

Open **Payments** from a managed clinic card. The protected route is
`/clinic-admin/clinics/<tenant UUID>/payments`. B07 uses authenticated billing
history, payment snapshots, cursor pagination and independent commission totals.
History loads newest payments first across all pages, with payment ID as a stable
tie-breaker for equal creation times.
See [B07 setup and verification](../../../../../docs/B07-live-billing.md).

Purpose changes both history and totals; status changes only history. The server
controls authorization and immutable commission snapshots. Loading and errors
show explicit states, with no synthetic rows or substitute totals. Refund review
allows clinic admins to issue full consultation refunds with a required reason and
confirmation. Medication/delivery payments have no refund action. See
[`services/billing/REFUNDS.md`](../../../../../services/billing/REFUNDS.md).
Totals come from the billing API.
