# D02 sandbox delivery quotations

The fulfilment service obtains real SG Lalamove sandbox quotations, refreshes
current clinic catalogue prices and stores immutable SGD quote snapshots. It
never accepts browser totals, coordinates, quantities or provider identifiers.
No delivery is submitted by these endpoints.

## Setup

Run `python -m alembic upgrade head` as the restricted fulfilment database role;
migration `0002` adds `quotes`, `quote_requests` and one-active-quote-per-order
uniqueness. Existing D01 orders are preserved. Readiness requires both order and
quote tables. No shared Compose, routing, contract or infrastructure changes are needed.

Set `SERVICE_LALAMOVE_API_KEY` and `SERVICE_LALAMOVE_API_SECRET` to sandbox
credentials, and `SERVICE_DELIVERY_LOCATIONS_PATH` to a private JSON file:

```json
{
  "origins": {
    "11111111-1111-4111-8111-111111111111": {
      "address": "1 Raffles Place, Singapore 048616",
      "coordinates": {"lat": "1.2844", "lng": "103.8511"}
    }
  },
  "destinations": {
    "038983": {"lat": "1.2935", "lng": "103.8572"}
  }
}
```

Replace the example tenant UUID with the owning clinic's UUID and configure its
dispatch address. Coordinates are decimal strings. The prototype supports an
operator-maintained directory of destination postcodes, with server-owned
coordinates; it does not implement address search/geocoding. Add verified
postcodes needed for the demo. Address lines allow unit details, require 1–300
characters and reject control characters. Postcodes require six digits and
country must be `SG`. The patient must supply the address matching that postcode;
the service does not establish residence or verify unit details. Arbitrary
Singapore address coverage/geocoding is a suggested follow-up, outside D02.

Missing credentials/directory/clinic origin returns 503 `delivery_unavailable`;
unsupported destination postcodes return 422 `unsupported_destination`. Invalid
configured JSON fails startup. Both credentials are required together and
production key prefixes are refused. The host is fixed to
`https://rest.sandbox.lalamove.com`, market SG, service MOTORCYCLE, two stops.
The X05 CLI's unprefixed `LALAMOVE_*` variables do not configure this application.

The adapter signs the exact UTF-8 request bytes, does not follow redirects, uses
15-second HTTP timeouts and never automatically retries a provider call. Invalid
SGD amounts, expiry, identifiers or mismatching coordinates fail closed with 503.
Provider IDs remain strings and decimal prices become exact integer minor units.
See [Lalamove's API reference](https://developers.lalamove.com/) for signing,
quotation stops and `expiresAt`.

## APIs and persistence

Direct service paths below use the existing authentication/current-identity
lookup. Ingress strips `/api/v1/fulfilment` as for D01.

| Route | Behaviour |
| --- | --- |
| POST `/orders/{order_id}/quotes` | Owning patient only; `Idempotency-Key` required; 201 new / 200 original replay |
| GET `/quotes/{quote_id}` | Owning patient or active owning-clinic admin; concealed 404 otherwise |

POST body:

```json
{
  "destination": {
    "address_line": "3 Temasek Boulevard",
    "postal_code": "038983",
    "country_code": "SG"
  }
}
```

The public quote shape follows C04: IDs, tenant, status, medication subtotal,
delivery fee, total, expiry and creation time. Responses contain neither addresses,
medication items nor provider references. Doctors and platform-only administrators
cannot read quotes. General request logging uses route templates and omits bodies.
Private quote rows retain destination, route/provider references and item/price
snapshots for future reservation/delivery consumers. Do not log or emit those
columns. Configure database storage/backups with the deployment's private-data
controls.

New keys refresh active catalogue names/prices using the order's frozen issued
quantities. Missing/inactive medicines return 409 `medication_unavailable`; unsafe
integer totals return 409 `amount_out_of_range`. Paid/refunded orders reject new
quotes with `already_paid`; pending payments, bound payment IDs and accepted quotes
reject with `payment_pending`. Other non-awaiting-payment orders are not quotable.

Expiry is `min(provider expiresAt, server_now + 10 minutes)`, never an assumed
provider lifetime. GET reports an active quote as expired at equality with its
deadline, without a background expiry worker. A new successful quote marks older
active rows expired or superseded, updates the order's current quote and totals,
and retains earlier immutable snapshots. Failed provider calls or database
transactions leave the previous quote and order snapshots intact.

Keys are scoped to subject plus quote-create operation and retained indefinitely
(at least C03's 24 hours). The fingerprint binds order and validated destination.
Different bodies conflict with 409 `idempotency_conflict`. Replay returns the
original response even after expiry/supersession/payment; use GET and the original
deadline to determine current usability. Replay never refreshes the fee or reopens
a quote. Database request-key locks, order row locks and catalogue row locks
serialize duplicate requests and repricing. Provider I/O holds these locks, so a
concurrent request can hit the existing database lock/statement timeout and must
retry with the same key. A provider quote followed by a process crash may leave
an unused provider quotation; retry can obtain another quote but cannot submit
a delivery or create two committed active quotes.

## Verification and boundaries

120 fulfilment tests passed on disposable PostgreSQL on 19 October 2026. The suite
checks migrations/drift/downgrade, access, totals, expiry equality and ten-minute
cap, immutable prior snapshots, concurrent same/different keys, failure rollback,
production credential refusal, exact outbound HMAC bytes and provider failures.
Ruff lint and formatting passed. Run the commands in `README.md`; use a fresh
disposable database because these tests truncate fulfilment tables.

A separate loopback HTTP check used the real sandbox adapter and PostgreSQL with
synthetic identity/dispensing fixtures and public landmark addresses. It created
a real SGD 7.80 quotation, combined it with a trusted SGD 20.00 medication subtotal
for SGD 27.80, read the operational quote and replayed the original response after
restarting the service. Provider expiry was `2026-10-19T07:55:36.502Z`. No delivery
order was created. Credentials and private provider references were not committed.

This establishes D02 sandbox quote integration, not end-to-end medication checkout,
real clinical-record dispensing integration, delivery dispatch or AWS operation.
The existing D01 dispensing fixture remains explicit. Checkout reservation and
billing acceptance must atomically lock the same order, recheck current quote,
patient, active status and `now < expires_at`, then freeze/bind payment state.
The reservation endpoint remains unfinished integration work; mocked B06 flows
do not establish it. D03–D06/I03 retain readiness, payment, delivery submission,
callback/reconciliation and complete medication journey work.
