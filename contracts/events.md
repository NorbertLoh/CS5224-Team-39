# C05: workflow events

Events carry resource IDs and minimal metadata, using [C01 conventions](api-conventions.md).
They describe committed facts and never contain clinical notes, prescriptions,
email addresses, tokens, credentials or payment-card data. Services retrieve
authorized details from the owning API. These contracts do not implement workflows.

## Envelope and transport

Publish to the configured EventBridge bus (`telelink-local` in Floci). Each
PutEvents entry has `Source` from the table below, `DetailType` ending in `.v1`,
`Time` equal to `occurred_at`, and `Detail` containing this JSON object:

| Field            | Required value                                                  |
| ---------------- | --------------------------------------------------------------- |
| `event_id`       | Server-generated UUID; stable across publication retries/replay |
| `schema_version` | Integer `1`                                                     |
| `occurred_at`    | Committed fact's UTC timestamp, RFC 3339 milliseconds with `Z`  |
| `tenant_id`      | Owning clinic's UUID                                            |
| `correlation_id` | UUID identifying the initiating workflow; propagated downstream |
| `data`           | Event-specific object from the table below                      |

SQS receives the full EventBridge JSON wrapper without an input transformer.
Consumers inspect `source`, `detail-type` and `detail`. EventBridge's outer `id`
and the SQS message ID are transport identifiers, not deduplication keys.
Producers serialize `Detail` as JSON once; consumers parse the SQS `Body` once
and read its `detail` object. See [AWS event structure](https://docs.aws.amazon.com/eventbridge/latest/ref/events-structure.html).

## Producers and routes

All IDs below are UUID strings. Payment `amount` uses C01 Money and is the
trusted committed charge snapshot. Payment purposes have separate event types.

| DetailType                          | Source                      | Required `data` fields                                                                       | Consumers    |
| ----------------------------------- | --------------------------- | -------------------------------------------------------------------------------------------- | ------------ |
| `consultation_payment_succeeded.v1` | `telelink.billing`          | `payment_id`, `appointment_id`, `amount`                                                     | scheduling   |
| `medication_payment_succeeded.v1`   | `telelink.billing`          | `payment_id`, `order_id`, `amount`                                                           | fulfilment   |
| `appointment_confirmed.v1`          | `telelink.scheduling`       | `appointment_id`                                                                             | notification |
| `prescription_issued.v1`            | `telelink.clinical-records` | `prescription_id`, `appointment_id`                                                          | document     |
| `medical_certificate_issued.v1`     | `telelink.clinical-records` | `medical_certificate_id`, `appointment_id`, `patient_id`, `doctor_id`                        | document     |
| `document_ready.v1`                 | `telelink.document`         | `document_id`, `appointment_id`, exactly one of `prescription_id` / `medical_certificate_id` | notification |
| `delivery_status_changed.v1`        | `telelink.fulfilment`       | `delivery_id`, `order_id`, `status`                                                          | notification |

Delivery `status` is the fulfilment service's normalized, nonempty status string;
C04/D06 define legal values and transitions. C03/C04 own payment and booking
state rules. A consultation payment does not override an expired hold; scheduling
applies the late-payment policy. Fulfilment records payment but submits delivery
only when its own paid AND ready conditions are met.

U17 adds MC issuance after consultation has durably ended and scheduling has accepted
completion. Clinical records seals the saved MC decision and stages the issuance event
in one transaction. MC dates, additional notes and private consultation notes are never
placed on the event bus. The document service fetches a context-bound, audited issued
MC projection. MC `document_ready.v1` carries `medical_certificate_id`; prescription
ready events retain their existing shape with `prescription_id`. Consumers must branch
on the source ID instead of assuming every ready document is a prescription.
The document queue's source/type allowlist now includes both clinical issuance events;
rerun the F12 bootstrap to update existing rules. See [U17 handoff and setup](../docs/medical-certificates.md).

## Local resource mapping

F12 bootstraps one standard SQS queue and one EventBridge rule per consumer,
matching exact source/type pairs above. Notification has three allowed pairs;
do not admit an unlisted source/type cross-product. Queue names are
`telelink-local-<consumer>` and rule names `<consumer>-events`, for consumers
`scheduling`, `fulfilment`, `document` and `notification`.

Each consumer queue has a `telelink-local-<consumer>-dlq`, visibility timeout
30 seconds, four-day retention and `maxReceiveCount=3`. Consumer DLQs retain
messages for 14 days. A shared `telelink-local-event-delivery-dlq` (14 days)
captures EventBridge target-delivery failures. Each target has three retry
attempts and a maximum event age of one hour. Policies allow
`events.amazonaws.com` to send only from the corresponding rule ARN; the
delivery DLQ allows the four rule ARNs. These are separate failure stages:
[EventBridge target DLQs](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html)
and [SQS consumer DLQs](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html).

## Delivery and versioning rules

- Publishers commit state and outbox data together. Retries preserve the
  original envelope and event ID; retry failed PutEvents entries, not successful
  siblings. M02 implements publication and retry tracking.
- Delivery is at least once and can arrive out of order. Consumers record
  `(consumer, event_id)` in their own inbox with the state change, then delete
  SQS messages after success. M03 implements acknowledgement, deduplication and
  retries; external side effects need their own idempotency key.
- Validate source/type, version, IDs, tenant/resource context and required
  fields. Tenant IDs are context, not authorization. Unknown versions and
  malformed payloads are not acknowledged as success; bounded receives move
  them to the consumer DLQ.
- Additive optional fields retain `.v1`; consumers ignore unknown optional
  fields. Changing a required field or its meaning requires a new version and
  coordinated routing/consumer rollout.
- Replay retains `event_id` and `correlation_id`. Resolve the cause before
  replay; M04 documents and verifies the procedure. Synthetic F12 delivery
  verifies routing only, not business integration or all DLQ/restart behavior
  (M03/M04/F16).

## Synthetic fixtures

[`examples/workflow-events.json`](examples/workflow-events.json) contains six
PutEvents entries, one per event type. IDs and amounts are synthetic. `Detail`
is a JSON string as required by PutEvents. Production publishers supply their
own committed facts and configured bus name.
