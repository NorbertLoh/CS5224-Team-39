# C01: shared HTTP API conventions

This is the common contract for new TeleLink business APIs and their frontend
consumers. C02-C05 define domain resources, access rules, states and events using
these conventions. Changes to shared fields must be coordinated with consumers
in a linked issue/PR. Examples below are synthetic contract fixtures, not live
endpoints or evidence of integration.

## Transport and service prefixes

Business APIs use JSON (`Content-Type: application/json`) and snake_case field
names. Clients send `Accept: application/json`; send Content-Type only when a
JSON body is present. Resource responses are direct JSON objects; lists use the
pagination envelope below. Successful creation returns 201; ordinary reads and
updates return 200; a successful action without a body returns 204. Clients must
not try to parse a 204 response. Binary document downloads and provider webhooks
have explicitly documented media types in their owning contracts.

All public business routes use `/api/v1/<service>`:

| Service | Public prefix |
| --- | --- |
| Identity | `/api/v1/identity` |
| Tenant | `/api/v1/tenant` |
| Scheduling | `/api/v1/scheduling` |
| Consultation | `/api/v1/consultation` |
| Clinical records | `/api/v1/clinical-records` |
| Billing | `/api/v1/billing` |
| Document | `/api/v1/document` |
| Fulfilment | `/api/v1/fulfilment` |
| Notification | `/api/v1/notification` |

Use plural resource segments, for example
`/api/v1/scheduling/appointments/{appointment_id}`. Domain contracts define exact
routes and methods. The browser API base defaults to `/api/v1`; service paths are
appended once. For a different origin, configure an absolute base ending in
`/api/v1`. Do not append a deployment stage prefix in browser feature code.

For proxied deployments, the proxy strips `/api/v1/<service>` before forwarding
to the owning service. Service-local routers use paths such as `/appointments`.
Set `SERVICE_ROOT_PATH=/api/v1/<service>` for generated external URLs/OpenAPI;
`root_path` is not a router prefix. Ingress configuration must remove any API
Gateway stage prefix as well. F10/W04/W20 implement and verify these mappings;
this document does not change deployment configuration.

Direct service probes remain `/health/live` and `/health/ready`; docs remain
`/docs` and `/openapi.json` when enabled. They are operational endpoints outside
the business contract. PeerJS signalling stays under `/peerjs`, not this HTTP
API namespace. Internal service APIs require their own documented authentication
and access rules; they are not implicitly public.

## IDs and identity

New application resource IDs are server-generated UUIDs serialized as canonical
lowercase, hyphenated strings. Store them as UUIDs where supported. Clients treat
them as opaque strings: never infer ordering, role, ownership or tenant from an
ID. Field names are explicit (`appointment_id`, `tenant_id`, `patient_id`) rather
than overloaded identifiers. URL-encode dynamic path segments.

External IDs such as Cognito `sub` and provider references remain opaque strings
in explicitly named fields; do not force them into the application UUID format.
Clinic slugs are display/lookup values, not resource IDs or authorization claims.
Foreign resource IDs link independent services; they do not permit cross-service
table writes. A browser-supplied tenant ID is selection input only. Services must
validate authenticated membership and resource context as specified by C02.

Protected requests use `Authorization: Bearer <access_token>`. Never accept ID
tokens, arbitrary identity headers, or client roles as proof of access. Token
acquisition, refresh and expiry UX belong to A01/A02; services enforce access.

## Money

Represent money as an object with `amount_minor` (integer) and `currency`
(uppercase three-letter currency code). Initial prices use SGD. For SGD, 2500
minor units represents SGD 25.00. Never serialize monetary amounts as floating
point major-unit values or formatted strings.

```json
{"amount_minor": 2500, "currency": "SGD"}
```

Prices and totals are nonnegative. Signed adjustments must be explicitly defined
by the owning domain contract. Values must be safe JSON/JavaScript integers
(absolute value at most 9007199254740991); services impose smaller business
limits. Only combine matching currencies. Price authority, commission snapshots,
rounding and payment purposes belong to C03/C04; a client-calculated total is not
a trusted charge amount.

## Timestamps and optional fields

Serialize instants as UTC RFC 3339 strings with millisecond precision and `Z`,
for example `2026-10-12T03:00:00.000Z`. APIs normalize accepted offset-bearing
timestamps to UTC and reject timezone-free instants. Use explicit names such as
`created_at`, `updated_at`, `expires_at`, `starts_at`, and `ends_at`. Display them
in Asia/Singapore in the UI; do not send display-formatted local times to APIs.

A date-only value is `YYYY-MM-DD` in a separately defined date field, never an
instant. Scheduling contracts define calendar/timezone semantics and intervals.
Expiry rules use the server clock; browser countdowns are informational.

Contracts specify required versus optional fields. `null` means an explicitly
absent value; an omitted field is not automatically equivalent. For PATCH,
omission means unchanged, and null clears a field only if that field permits it.
Clients ignore unknown additive response fields. Breaking changes require a new
API version or an agreed coordinated migration; removed fields, type changes and
new required inputs are breaking changes.

## Errors and correlation

Non-2xx business responses use the following envelope, with the HTTP status
representing the failure. Do not return an error disguised as a successful 200.

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more fields are invalid.",
    "request_id": "synthetic-request-001",
    "details": [
      {"field": "body.starts_at", "code": "invalid_timestamp", "message": "Use a timestamp with a timezone."}
    ]
  }
}
```

`error.code` is a stable lowercase snake_case machine code. `message` is safe
human-readable text, not a stack trace or database/provider error. `request_id`
is required and matches the response `X-Request-ID`. `details` is a required
array (empty for errors without field details). Each detail has `field`, `code`
and `message`; use locations like `body.starts_at` or `query.limit`. Never include
rejected values, tokens, clinical content or other sensitive data in errors.

| Status | Common code | Meaning |
| --- | --- | --- |
| 400 | `bad_request` | Malformed request |
| 401 | `unauthenticated` | Missing, invalid or expired access token |
| 403 | `forbidden` | Authenticated caller lacks permitted access |
| 404 | `not_found` | Resource absent or concealed by access policy |
| 409 | `conflict` | State or uniqueness conflict |
| 422 | `validation_error` | Invalid field value |
| 429 | `rate_limited` | Rate limit reached |
| 500 | `internal_error` | Unexpected server failure |
| 502 | `upstream_error` | Dependency returned an invalid response |
| 503 | `unavailable` | Temporary unavailability |
| 504 | `upstream_timeout` | Dependency timed out |

Domain contracts may specialize codes (for example `slot_unavailable` with 409)
while preserving this envelope. Do not reveal another tenant's resource existence;
C02 specifies when to conceal it with 404. Clients handle codes, not message text.

The existing template accepts `X-Request-ID` only when it contains 1-64 ASCII
letters, digits, dots, underscores or hyphens; otherwise it generates a UUID.
Correlation is not authentication. Cross-origin servers expose `X-Request-ID`
and `Retry-After` to browsers and allow the required request headers using an
explicit CORS origin allowlist.

429/503 may include `Retry-After` in seconds or as an HTTP date. Automatically
retry only bounded, safe reads for transient failures. Do not automatically retry
mutations or 401/403/422 responses. Domain contracts explicitly define idempotency
keys and reconciliation for side effects. Cancellation is not a user-facing error.
Clients must also handle network failures and non-JSON proxy errors using safe
fallback messages, without displaying raw response bodies.

## Cursor pagination

Collection requests accept `limit` (integer, default 25, range 1-100) and optional
`cursor` (opaque string from the preceding response). URL-encode query values.
The response has required `items` and `next_cursor` fields:

```json
{
  "items": [
    {"appointment_id": "6eb5c71e-b43a-44a3-96f8-7e71f3c51fe0", "starts_at": "2026-10-12T03:00:00.000Z"}
  ],
  "next_cursor": null
}
```

`next_cursor: null` marks the end; an empty list is
`{"items": [], "next_cursor": null}`. No total count or offset is implied.
Domain contracts define a stable ordering with an ID tie-breaker and allowed
filters. Services bind cursors to those filters, ordering and validated access
scope; a cursor never substitutes for authorization. Invalid, tampered, mismatched
or expired cursors return 422 (`validation_error`, detail field `query.cursor`).
Clients pass cursors unchanged, reset them when filters/clinic selection change,
and partition query keys by current authenticated context and filters. Concurrent
changes can alter subsequent pages; no snapshot consistency is promised.

## Adoption and verification

C01 documents the common contract only. The current FastAPI template has probes,
OpenAPI and request correlation, but no business routes or custom JSON error
handlers. Its default FastAPI errors and operational probe responses do not yet
implement this envelope. Owning API tasks must add their local handlers for
validation, domain and unexpected errors and publish OpenAPI snapshots/fixtures;
do not silently change the template as part of C01. F08 consumes these types and
handles nonconforming transport errors defensively.

Consumer review checklist for subsequent domain/API PRs:

- Confirm route prefix/stripping, snake_case fields, opaque IDs, integer money
  and normalized UTC instants in sanitized examples.
- Verify an empty/end list and invalid cursor, a 204 response, and a safe
  validation/authentication error with matching correlation header.
- Validate authenticated scope independently of supplied IDs and cursors.
- Confirm frontend query keys and error handling against the published fixtures.

These are adoption criteria, not claims that integration is complete. C02-C05,
F10 and authentication/deployment tasks retain their original scope.
