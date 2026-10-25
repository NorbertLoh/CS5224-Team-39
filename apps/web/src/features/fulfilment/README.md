# Fulfilment

Clinic admins can use Add / edit medications on a card to correct the actual
issued prescription with an audited replacement. Status-coloured card borders
remain visible while expanded. See [prescription corrections](../../../../../docs/prescription-corrections.md)
for the revision/history, unpaid-order replacement and financial/preparation locks.

Patient orders are at `/patient/medication-orders`; owning-clinic orders are at
`/clinic-admin/clinics/<tenant UUID>/orders`. Setup, service credentials, worker
commands, recovery and sandbox evidence are in
[the live fulfilment guide](../../../../../docs/D07-live-fulfilment.md).

`LiveOrders` and `OrderWorkspace` load authorized order lists and snapshots.
`LiveMedicationCheckout` requests trusted quotes and opens hosted payment;
`LiveMedicineReadiness` persists clinic preparation actions. Tracking displays
server delivery states and guidance for uncertain outcomes or refund review.
These components use live APIs and do not generate example orders.

Clinic Medicine & delivery uses the selected clinic's name and navigation in the
shared management navbar. It does not repeat a clinic UUID or a back-to-clinics
link in the page body; Change clinic remains available in the navbar.

The clinic page has one list of medicine cards combining issued prescriptions
and their orders. Cards for prescriptions awaiting an order contain editable
pricing and a disabled preparation action. In each expanded order card, Medication pricing shows
its saved unit prices, quantities and totals before the Medicine preparation
card and Mark medicine ready action. Order snapshots remain locked; readiness
and payment/delivery gating use the existing APIs. Pricing is no longer rendered
on the Manage clinics dashboard, and there is no separate pricing section or
side details panel. No new routes or setup are required.

Order borders and text labels show payment/preparation waits, delivery progress,
completion and problems requiring review. Selection preserves the status border.
Every clinic medicine/order card starts collapsed, including order links. Open
or close a card with its header; prescription headers also support keyboard
activation and preserve unsaved prices while collapsed.

Patient Orders & delivery shows a Review medicines & pay button directly in
each collapsed unpaid order card that can start checkout. It expands that
order's existing medicines, address, quote and payment controls.

Run `npm run lint` and `npm run build` from `apps/web`. To verify integration,
follow [the actual medication payment and delivery journey](../../../../../docs/I03-local-journey.md).
