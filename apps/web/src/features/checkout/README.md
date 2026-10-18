# Checkout status

B07 connects `/patient/checkout` to authenticated billing and scheduling reads.
Open it from booking review or **Payment status and checkout** in an appointment.
See [B07 setup, return handling and verification](../../../../../docs/B07-live-billing.md).

`/patient/checkout-preview` remains a separately labelled synthetic preview.
Its fixed historical snapshots demonstrate pending, failed, confirmation, expiry,
refund and unavailable-reference states. Preview buttons change only the selected
fixture state. Live pages never read these fixtures or infer success from redirect
parameters. Payment success must also have scheduling confirmation before the
live page announces a confirmed booking.
