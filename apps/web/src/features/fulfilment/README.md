# Fulfilment

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

Order borders and text labels show payment/preparation waits, delivery progress,
completion and problems requiring review. Selection preserves the status border.

Run `npm run lint` and `npm run build` from `apps/web`. To verify integration,
follow [the actual medication payment and delivery journey](../../../../../docs/I03-local-journey.md).
