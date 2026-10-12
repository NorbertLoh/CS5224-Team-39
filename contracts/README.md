# API and event contracts

C01-C05 define common fields, access APIs, booking/payment states, prescription/order boundaries and event envelopes. Store reviewed contracts and sanitized fixtures here so frontend and backend tasks can proceed independently.

[C01 shared HTTP API conventions](api-conventions.md) defines resource IDs, money, UTC timestamps, errors, cursor pagination and versioned service prefixes for frontend and service consumers. It includes synthetic examples and identifies current template adoption gaps. Domain payloads, access rules, states and events remain C02-C05 work. Coordinate contract changes with consumers in the relevant issue/PR; later tasks add OpenAPI snapshots and event schemas.
