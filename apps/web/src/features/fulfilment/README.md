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

Clinic Medicine Pricing is at `/clinic-admin/clinics/<tenant UUID>/medicine-pricing`
and lists issued prescriptions with their pricing controls. Medicine Delivery uses
the existing orders route for preparation and tracking. Expanded order cards show
the saved price breakdown and preparation controls. The clinic navigation counts
unlocked prescriptions with missing prices and paid orders awaiting preparation.

Order borders and text labels show payment/preparation waits, delivery progress,
completion and problems requiring review. Selection preserves the status border.
Every clinic medicine/order card starts collapsed, including order links. Open
or close a card with its header; prescription headers also support keyboard
activation and preserve unsaved prices while collapsed.


Run `npm run lint` and `npm run build` from `apps/web`. To verify integration,
follow [the actual medication payment and delivery journey](../../../../../docs/I03-local-journey.md).
