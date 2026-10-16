# Clinic booking

S07 loads real slots for a chosen Singapore date and creates a real expiring hold.
`LiveCheckout` polls appointment detail and releases an active booking before changing
time. Billing checkout remains B07 and is explicitly unavailable in the review.
See [setup, boundaries and verification](../../../../../docs/scheduling-frontend.md).

`ClinicBooking` loads clinic and doctor metadata; `BookingFlow` coordinates real slot
queries and holds. Slot display components remain shared. The older `fixtures` and
`CheckoutReview` are retained only for fixture tests and are not mounted.
