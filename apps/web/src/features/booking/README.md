# Clinic booking

S07 loads real slots for a chosen Singapore date and creates a real expiring hold.
`LiveCheckout` polls appointment detail and releases an active booking before changing
time. The booking review links to authenticated live billing checkout and status (B07); see `docs/B07-live-billing.md` for setup.
See [setup, boundaries and verification](../../../../../docs/scheduling-frontend.md).

`ClinicBooking` loads clinic and doctor metadata; `BookingFlow` coordinates real slot
queries and holds. Slot display components use types from the scheduling API.
