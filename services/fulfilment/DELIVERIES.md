# Guarded delivery submission (D05)

RF14 checkout now saves a confirmed recipient on each new quote. Delivery
preparation uses that saved contact instead of a later Profile lookup. The Profile
and directory lookups below apply to legacy quotes without a recipient. Prepared
delivery requests retain their original payload. See
[checkout contacts](../../docs/RF14-checkout-contacts.md).

The separate delivery worker submits an order only when fulfilment has
`status=paid`, `payment_status=succeeded`, and `medicine_status=ready`.
Submission remains independent of the API and payment consumer, so either arrival
order is supported. The database enforces one delivery record per order, one stable
operation ID per attempt, and unique provider order references.

## Setup

Apply `python -m alembic upgrade head` before starting the updated API or worker.
Migration `0004` adds `fulfilment.deliveries` and the service-owned event outbox;
readiness checks require both. Existing API paths remain unchanged except the new
authorised `GET /deliveries/{delivery_id}`. Its six operational fields are delivery,
order and tenant IDs, status, and creation/update timestamps. The owning patient,
current owning-clinic admin and platform operational role can read it. Contacts,
addresses, provider IDs, request payloads and share links are never returned.

Use the D02 sandbox credentials and the D04 billing URL/service credential.
Set `SERVICE_DELIVERY_CONTACTS_PATH` to a private JSON file with trusted contacts:

With the Clinic Settings tenant connection configured, the worker obtains the
clinic sender's name and phone from the saved pickup contact instead of the file's
`senders` section. With `SERVICE_PROFILE_SECRET` configured, the worker reads
patient recipient names/phones from [saved patient profiles](../../docs/patient-profile.md);
otherwise the file supplies patient `recipients`. Missing saved
clinic contact blocks preparation without falling back to a file sender.
See [clinic pickup settings](../../docs/clinic-pickup-settings.md).

```json
{
  "senders": {
    "11111111-1111-4111-8111-111111111111": {
      "name": "Synthetic clinic",
      "phone": "+6580000000"
    }
  },
  "recipients": {
    "22222222-2222-4222-8222-222222222222": {
      "name": "Synthetic recipient",
      "phone": "+6580000001"
    }
  }
}
```

Replace the keys with the owning clinic's tenant ID and recipient patient's ID.
This is a prototype operator-managed directory, loaded at worker startup. Restart
after changing it. Use only synthetic contacts for sandbox verification. Names
and Singapore telephone numbers are validated, with no built-in contact defaults.
Do not commit the file or pass its contents through browser requests or events.
The minimal provider request needs these contacts and the frozen route; it contains
no medicine names, clinical notes or prescription content. Prepared requests are
retained privately for reconciliation.

Run these separate processes from `services/fulfilment`:

```powershell
python -m app.delivery_worker --once
python -m app.delivery_worker
python -m app.delivery_worker --resolve
python -m app.delivery_worker --publish
```

Default mode claims eligible orders and submits pending attempts. `--once` handles
one bounded batch. `--resolve` retries durable billing refund-required flags; it
does not execute refunds. `--publish` uses M02 to publish pending delivery status
events, requiring `SERVICE_EVENT_BUS_NAME`. Local SDK configuration and dummy
credentials follow [PAYMENTS.md](PAYMENTS.md); AWS uses task-role credentials and
no emulator override. No root Compose, contract, frontend or infrastructure edits
are included. Deploy/run these workers explicitly.

## Gate and price checks

The worker locks the order to claim `paid -> submitting`, inserts a pending
delivery, assigns its local delivery ID to the order, and stages the pending event
in one transaction. Concurrent claims skip locked rows. Before any order submission,
the worker rechecks the paid/ready gate, accepted quote, tenant, patient, frozen
amounts and authoritative billing payment through the scoped internal API.

Billing's `updated_at` must be present and precede the accepted quote deadline.
This conservatively treats a success snapshot at or after that deadline as late.
Such orders become `exception` / `refund_required`, with a durable `quote_expired`
resolution request to billing. D04 records payment truth; D05 prevents late success
from starting delivery.

For timely payment whose medicine becomes ready later, the sandbox adapter obtains
a fresh provider quotation for the accepted quote's exact frozen addresses and
coordinates. It does not use new catalogue prices or changed clinic locations.
The new fee must equal the frozen paid fee. Any increase **or decrease** becomes
`exception` / `refund_required`, with reason `delivery_price_changed`; no additional
charge is made. A fresh, unexpired quote and unchanged fee are persisted with the
prepared request. Billing/configuration/provider quotation outages before sending
retain pending state, with bounded exponential backoff (10–300 seconds).

The resolution sender uses billing's authenticated
`POST /internal/payments/{id}/resolution`, validates its response, and records
acknowledgement durably. Failed sends remain pending; a crash after remote success
can safely repeat the idempotent request. Billing validates its own checkout attempt
and reservation; missing integration fixtures cannot bypass those checks.

## Uncertain outcomes and recovery

The provider's [API reference](https://developers.lalamove.com/#headers) describes
`Request-ID` as a nonce for tracing, without promising idempotent order creation.
D05 therefore never automatically repeats `POST /v3/orders` for a delivery.

Before sending, the worker commits `status=unknown`, the stable operation ID,
`send_started_at`, fresh quote and exact request. The operation ID is sent as
Request-ID and alongside the local delivery ID in provider metadata. A verified
acceptance records the provider ID, changes delivery to `submitted`, changes order
to `dispatched`, and stages its event atomically. Validation checks metadata, quote,
SGD fee and exact route. Explicit rejection becomes failed/exception; timeouts,
5xx, redirects, malformed or conflicting responses remain unknown. A valid numeric
provider ID is retained even when the rest of the response cannot be verified.

An unknown record can mean a response was lost, acceptance could not be persisted,
or the process stopped after recording intent but before sending. It is deliberately
excluded from automatic resubmission. Inspect the sandbox partner portal/provider
support using the recorded operation metadata and Request-ID to identify the order.
Then reconcile the independently retrieved provider reference:

```powershell
python -m app.delivery_worker --reconcile DELIVERY_UUID --provider-order-id PROVIDER_ID --operator YOUR_NAME
```

Use actual IDs in that command. The CLI performs an authenticated provider GET and
checks the reference, both metadata IDs, fresh quote ID, route and unchanged fee.
It cannot accept an operator assertion alone or replace a conflicting stored
reference. Successful reconciliation records the operator and timestamp. Repeating
it is safe. A verified cancelled/rejected/expired provider order becomes a failed
delivery and an exception order. Accepted orders become submitted; tracking their
later progress is handled by the [D06 poller](TRACKING.md).

If no provider reference can be established, leave the attempt unknown and resolve
it with the provider. There is no force-resend or retry-failed command in D05.
Never clear `send_started_at`, delete the delivery, or manually reset an order to
paid to retry. A future explicit retry flow must first prove the old outcome and
record an audited operator decision. Definite submission failures require manual
payment/refund review; they are not falsely reported as completed delivery.

Every committed normalized change stages `delivery_status_changed.v1` in the
outbox, including pending, unknown, submitted and failed. Publication retries
retain event IDs and never invoke provider order creation. Unknown is an honest
submission-intent state, which may briefly be visible while the request runs.

## Verification and remaining integration

On 19 October 2026, the local full suite passed 265 PostgreSQL/API/protocol tests;
all 24 focused provider/configuration checks also passed after the final private
contact error-sanitization change. Coverage includes
migration drift/round trips, restricted schema access, six concurrent workers,
payment/readiness gating, late payment and changed prices, scoped billing reads
and resolution writes, claim/outbox rollback, crashes before POST and after
provider acceptance, uncertain responses, reconciliation, delivery access, and
publication without resubmission. Ruff lint/format also passed.

The actual SG sandbox check created order `3609269479148278516` for a frozen SGD 7.80
delivery fee using synthetic landmark stops and contacts. The real billing API read
an explicitly seeded succeeded payment. After actual provider acceptance, the test
simulated a lost response: a separate restarted worker made no second submission.
The reconciliation CLI independently retrieved the order, recovered it once and
returned no change on repetition. Pending/unknown/submitted outbox entries were
verified. The fixture order was then cancelled directly in the sandbox, and GET
confirmed `CANCELED`; this cleanup is not evidence of D06 application tracking.

Clinical dispensing and the fulfilment checkout-reservation endpoint remain
unfinished, so these checks use explicit synthetic accepted reservations and
billing payment rows. No Stripe charge, real patient delivery, AWS deployment,
driver pickup/completion, callbacks or full I03 journey is claimed. D06 implements
ongoing [verified polling](TRACKING.md); application cancellation and automatic refunds
remain separate work. Run the full suite using the disposable setup in [README.md](README.md).
