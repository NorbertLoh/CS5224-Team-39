# Payment processing and success publication (B04)

B04 drains verified Stripe receipts, commits validated payment transitions with
the receipt and C05 success event, and publishes the stored outbox through M02.
Payment status/list APIs and medication checkout remain B05/B06.

Worker configuration and verification will be recorded before review.
