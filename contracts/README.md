# API and event contracts

C01-C05 define common fields, access APIs, booking/payment states, prescription/order boundaries and event envelopes. Store reviewed contracts and sanitized fixtures here so frontend and backend tasks can proceed independently.

[C04 prescriptions, orders and quotes](prescription-order-quote.md) proposes
dispensing projections, trusted prices, quote expiry and paid AND ready delivery
gating, with [synthetic workflow examples](examples/prescription-order-quote.json).
Consumer review is pending; these documents do not implement clinical/provider flows.

[C01 shared HTTP API conventions](api-conventions.md) defines resource IDs, money, UTC timestamps, errors, cursor pagination and versioned service prefixes. [C05 workflow events](events.md) defines the event envelope, producer/consumer routes and synthetic PutEvents examples. Domain APIs, access rules and state transitions remain C02-C04 work. Coordinate changes with consumers in the relevant issue/PR; later tasks implement validation and integrations.
