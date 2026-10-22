# Clinic payments

Open **Payments** from a managed clinic card. The protected route is
`/clinic-admin/clinics/<tenant UUID>/payments`. B07 uses authenticated billing
history, payment snapshots, cursor pagination and independent commission totals.
See [B07 setup and verification](../../../../../docs/B07-live-billing.md).

Purpose changes both history and totals; status changes only history. The server
controls authorization and immutable commission snapshots. Loading and errors
show explicit states, with no synthetic rows or substitute totals. Refund review
is guidance only; this page does not initiate refunds or payouts. Totals come from the billing API.
