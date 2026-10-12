# API and event contracts

C01-C05 define common fields, access APIs, booking/payment states, prescription/order boundaries and event envelopes. Store reviewed contracts and sanitized fixtures here so frontend and backend tasks can proceed independently.

[C02 identity, clinic and appointment access](identity-clinic-access.md) proposes
resource shapes, role/membership policy and access decisions, with
[synthetic access examples](examples/access.json). Consumer review is pending;
these documents do not implement authorization.

[C01 shared HTTP API conventions](api-conventions.md) defines resource IDs, money, UTC timestamps, errors, cursor pagination and versioned service prefixes. [C05 workflow events](events.md) defines the event envelope, producer/consumer routes and synthetic PutEvents examples. Domain APIs, access rules and state transitions remain C02-C04 work. Coordinate changes with consumers in the relevant issue/PR; later tasks implement validation and integrations.
