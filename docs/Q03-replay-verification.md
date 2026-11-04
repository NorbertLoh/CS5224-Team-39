# Q03: local payment, delivery and DLQ replay

Verified on 25 October 2026 against the retained actual I03 journey. Replays
preserved the original payment, receipt, order, inbox, delivery and outbox rows.
The dedicated source/DLQ pair was drained and deleted. No application queues were
consumed, no inbox rows were removed and no payment or courier order was created.

## Setup and rerun

Use the configured host checkout from [I03](I03-local-journey.md), its service
virtualenvs, persistent database on `55411` and Floci on `4566`. Keep the original
journey records intact. These probes use the service-owned billing/fulfilment
roles and reject nonlocal targets. They do not migrate or reset data. Pause other
workers while comparing snapshots; unrelated activity on the target can correctly
make an equality check fail. Keep credentials and logs in ignored local files.

The billing probe needs the original Stripe test key, a configured local webhook
secret and network access to read the original Stripe event. It starts a temporary
real billing HTTP receiver on an exclusively bound ephemeral loopback port, using
the same Settings instance as its database checks. An unrelated running receiver
cannot be selected. It retrieves a genuine provider snapshot
and signs its unchanged event content with the current local secret. This is an
operator replay, not a new Stripe-initiated callback or hosted payment.

The observed receiver used the existing billing `0005` schema and original
webhook tables. Only its live endpoint and webhook route were exercised; this
does not claim readiness for the newer refund feature or the full application.
No persistent migration was needed. Fresh setups should follow the current
service setup guide separately.

From the repository root, using the retained I03 identifiers:

```powershell
services/billing/.venv/Scripts/python.exe tests/e2e/replay_q03_billing.py daf96f94-fa4c-4f15-a788-28ab66fbff9f
services/billing/.venv/Scripts/python.exe tests/e2e/replay_q03_billing.py ce8c60a3-0da2-4c89-ae8f-403df25d84d1
services/fulfilment/.venv/Scripts/python.exe tests/e2e/replay_q03_fulfilment.py 05a21d8b-bef9-4b37-a274-e938bfe6acb6
```

Use `--config-root <configured-checkout>` when running from a separate source
worktree. Commands print check names only; provider bodies, signatures, database
credentials and private delivery payloads remain in memory. The temporary receiver
is stopped and joined on success or failure; it does not remain as a background service.

## Observed evidence

Billing replay covers both purposes: consultation payment
`daf96f94-fa4c-4f15-a788-28ab66fbff9f` and medication/delivery payment
`ce8c60a3-0da2-4c89-ae8f-403df25d84d1`. Each has one processed Checkout receipt
and one published success event. The original provider event matched its stored
Checkout/payment IDs, payment reference, paid state and amount. A modified-body
request returned `400` with no stored change. Four concurrent correctly signed
requests returned `200`, leaving the complete target payment, receipt collection
and success-outbox rows unchanged. Existing payment-intent receipts also remained
unchanged. Each billing run passed all ten checks.

The fulfilment probe reads the original published medication-payment event from
billing's outbox and checks its order, payment and tenant against the retained
order and committed fulfilment inbox. It reconstructs a minimal EventBridge
wrapper from that outbox; the original C05 detail and event ID are preserved,
while the historical raw SQS transport wrapper was not retained. It runs the same `consume_batch` and
transactional inbox implementation used by `app.payment_worker`. The real
`confirm_payment` handler is supplied; committed duplicates skip it.

Only acknowledgment is faulted: a small SQS wrapper performs real receives but
raises before `DeleteMessage`, simulating a crash/network failure after commit.
Floci's real redrive policy moves the unchanged event after three receives to a
unique `telelink-q03-<run>-dlq` queue. The probe confirms exactly three withheld
acknowledgments and no new handler effect, then sends the original body to its
original probe queue before deleting the DLQ copy. Recovery and another duplicate
each report `processed=0, duplicates=1, failed=0`; both queues drain. Application
queue policies are untouched; the probe uses a one-second visibility timeout and
the normal three-receive limit. Exit cleanup deletes only queues created by that
run. If interrupted, identify the run-specific pair before deleting leftovers.

Delivery `fa577d52-1d46-458b-be4b-6ecc7cb5ce8b` retains its original provider order
identity and sent intent. It is cancelled following I03's verified sandbox
cleanup. Two targeted calls to the actual worker's `submit_delivery` routine
return `False` before any billing/courier call. Explicit call guards fail the
probe if that boundary is crossed. Full order/delivery rows, delivery events and
the original inbox receipt remain equal; exactly one delivery remains. This
checks replay of historical submitted work, not a fresh dispatch or physical
delivery. Unknown/crashed-send handling is covered separately by existing tests.

Existing focused regressions passed against a separate disposable PostgreSQL
database: eight billing webhook/processing replay, concurrency and rollback tests,
plus four fulfilment acknowledgment, uncertain-send and post-dispatch replay tests.
Provider responses in those service tests are fixtures; the live probes above use
actual retained I03 records, Stripe event retrieval, HTTP, PostgreSQL and Floci.
Unrelated payment/order IDs were rejected before replay or queue creation. A
receiver-URL override was rejected before any Stripe retrieval or HTTP replay.

## Limits

This is local replay/recovery evidence for already-committed genuine journey
events. It does not establish first-time payment processing after a new handler
failure, a fresh courier submission, Stripe-initiated retry delivery, AWS SQS/DLQ
behavior, automatic refunds, or exactly-once external effects. M04 separately
covers rollback before the inbox/domain commit. Preserve original event IDs and
use the [operator replay procedure](messaging-replay.md); do not fabricate a new
success event or clear durable deduplication records to force processing.
