# Stripe webhook inbox (B03)

B03 adds raw-body signature verification and durable event-ID deduplication to
the billing API. Payment transitions and transactional success events belong to
B04; accepting a receipt does not confirm a payment.

Implementation and verification details will be recorded in this document before
the linked draft PR is ready for review.
