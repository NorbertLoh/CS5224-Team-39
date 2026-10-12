# API and event contracts

C01-C05 define common fields, access APIs, booking/payment states, prescription/order boundaries and event envelopes. Store reviewed contracts and sanitized fixtures here so frontend and backend tasks can proceed independently.

[C01 shared HTTP API conventions](api-conventions.md) defines resource IDs, money, UTC timestamps, errors, cursor pagination and versioned service prefixes. [C05 workflow events](events.md) defines the event envelope, producer/consumer routes and synthetic PutEvents examples. Domain APIs, access rules and state transitions remain C02-C04 work. Coordinate changes with consumers in the relevant issue/PR; later tasks implement validation and integrations.

C02-C04 domain proposals and synthetic examples are under consumer review in
[C02 identity/clinic/access PR #36](https://github.com/NorbertLoh/CS5224-Team-39/pull/36),
[C03 booking/payment PR #37](https://github.com/NorbertLoh/CS5224-Team-39/pull/37), and
[C04 prescription/order/quote PR #38](https://github.com/NorbertLoh/CS5224-Team-39/pull/38).
They do not implement live authorization, booking, clinical or provider flows.
