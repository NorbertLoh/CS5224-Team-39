# Clinic medicine readiness (D03)

`POST /orders/{order_id}/ready` returns the full current order with HTTP 200.
Send the access token as `Authorization: Bearer <token>` and omit the body (or send
`{}`). Fields supplied by the caller are rejected with 422. No idempotency key is
needed: readiness is a one-way, naturally idempotent action.

The service resolves current identity on each request. Only an active `clinic_admin`
membership in the order's owning tenant permits this action. Patient, doctor and
platform roles do not grant readiness permission. Missing orders and unauthorised
clinic access return 404; missing or invalid access tokens return 401.

Orders must be `awaiting_payment` or `paid`, with neither `refund_required` nor
`refunded` payment state. Other states return 409 `order_not_active`, including on
retries. The existing dispensing source must confirm an issued prescription with
the same prescription, patient, tenant and appointment IDs. Unissued prescriptions
return 409 `prescription_not_issued`; mismatched context returns 404. An unavailable
source fails closed with 503. Every retry rechecks permission and prescription state.

A PostgreSQL row lock serializes readiness with other order writers. The first
successful action persists `medicine_status=ready` and a server UTC `updated_at`
in one transaction. Retries preserve that timestamp and return the current order.
Failures roll back without changing readiness. Payment, prices, quote and delivery
fields remain unchanged. Ready-first orders continue waiting for payment; paid-first
orders retain `paid`. Delivery dispatch and its paid-AND-ready gate belong to D05.

No migration, additional environment variable or root routing change is required.
The direct service path is shown above; the normal ingress adds
`/api/v1/fulfilment`. Use the existing identity/token and database configuration.

The C04 dispensing HTTP adapter remains unfinished. As with D01, local verification
uses the explicit synthetic dispensing fixture (`SERVICE_DISPENSING_FIXTURE_PATH`)
or a controlled test source. The default source returns 503 and fixture mode is
rejected outside local/test. This does not establish real clinical-records,
medication-payment or delivery integration; those remain I03 and dependent tasks.

## Verification

Run the PostgreSQL suite and Ruff using the setup in [README.md](README.md).
The D03 cases cover owning-clinic access, revoked membership on retry, disallowed
roles and other clinics, inactive/refunded orders, prescription context and issued
state, unavailable-source rollback/retry, rejected request fields, durable reads,
both ready-first and paid-first states, and six concurrent requests returning the
same committed readiness timestamp. The signed-token boundary check also exercises
this endpoint with real RSA access-token verification and controlled identity HTTP
responses, including expiry, ID-token rejection and membership revocation.
