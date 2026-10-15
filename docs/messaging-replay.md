# Failed consumer jobs and replay (M04)

M02 and M03 are merged in PRs #97 and #99. This task verifies the remaining
failure path: a failed handler rolls back, SQS moves the message to its processing
DLQ, and an operator replays the unchanged event after fixing the failure.

## Reproduce locally

Start the pinned Floci service using the existing local setup. From the repository
root, use a configured service virtualenv containing boto3 and SQLAlchemy:

```powershell
services/scheduling/.venv/Scripts/python.exe dev/floci/check_dlq_replay.py
# For an isolated Floci instance on a different port:
services/scheduling/.venv/Scripts/python.exe dev/floci/check_dlq_replay.py --endpoint http://localhost:4567
```

The script imports the checked-out shared package directly. It creates two unique
`telelink-m04-*` queues and a temporary SQLite database, then deletes only those
queues and the temporary database on exit. It uses dummy credentials and refuses
non-loopback endpoints. It never purges or polls the application's consumer queues.
An interrupted process can leave its unique queues behind; identify that run's
queue names before deleting them.

The source queue uses `maxReceiveCount=3`, matching bootstrap, with a one-second
visibility timeout to shorten this synthetic test (application queues use 30s).
A real `consume_batch` handler inserts an effect and throws. Each retry must
leave both the inbox and effect tables empty. After three failures, the unchanged
message must arrive in the processing DLQ. The script sends that body back to
the source queue before deleting it from the DLQ, repairs the handler, verifies
one committed effect and acknowledgement, and sends a second copy to prove inbox
deduplication. It checks both queues are empty afterward.

## Operator procedure

1. Identify the failing consumer and its source queue and **processing DLQ**:
   `telelink-local-{scheduling,fulfilment,document,notification}-dlq` locally.
   The separate `telelink-local-event-delivery-dlq` is for EventBridge delivery
   failures; investigate target policy/routing there rather than using this
   consumer replay procedure.
2. Pause the affected worker while diagnosing recurring failures. Record the
   environment, queue ARN, event ID, correlation ID, error category and intended
   remediation in the incident/issue. Inspect payloads only in an authorised
   session; do not paste bodies or clinical data into logs or issues. Receiving
   a message changes its visibility and receive count, so allow it to become
   visible again if the investigation stops.
3. Fix the handler/configuration/downstream dependency first. Unknown event
   versions, misrouted messages and invalid envelopes need contract/routing
   remediation; repeatedly resending them does not repair them. Preserve the
   original `event_id`, tenant, correlation ID and occurrence time. Do not clear
   inbox rows to force an already completed event to run again. Reconcile any
   uncertain external side effect using its operation idempotency key first.
4. Replay one message to its original queue, at a rate the consumer can handle.
   The SDK sequence below preserves the original body and custom attributes.
   Run it in the service's authorised operator Python session, where `sqs`,
   `source_url`, `dlq_url` and `consumer` refer to the verified environment and
   queue pair. Use normal task/operator credentials on AWS, with no emulator
   endpoint override. Locally use the existing dummy credentials and endpoint.

```python
import json
from telelink_common.events import parse_sqs_body

source = sqs.get_queue_attributes(
    QueueUrl=source_url, AttributeNames=["RedrivePolicy"]
)["Attributes"]
dlq = sqs.get_queue_attributes(
    QueueUrl=dlq_url, AttributeNames=["QueueArn"]
)["Attributes"]
assert json.loads(source["RedrivePolicy"])["deadLetterTargetArn"] == dlq["QueueArn"]
messages = sqs.receive_message(
    QueueUrl=dlq_url, MaxNumberOfMessages=1, WaitTimeSeconds=1,
    VisibilityTimeout=60, MessageAttributeNames=["All"],
).get("Messages", [])
if messages:
    message = messages[0]
    event = parse_sqs_body(message["Body"], consumer=consumer)
    # Record event.event_id and event.correlation_id, without dumping the body.
    sqs.send_message(
        QueueUrl=source_url, MessageBody=message["Body"],
        MessageAttributes=message.get("MessageAttributes", {}),
    )
    sqs.delete_message(QueueUrl=dlq_url, ReceiptHandle=message["ReceiptHandle"])
```

5. Resume the consumer and verify its domain result, matching inbox row, source
   acknowledgement and DLQ drain. Watch for another failure before increasing
   replay volume. Never purge the DLQ as a substitute for successful recovery.

Sending must succeed before deleting from the DLQ. A timeout or crash between
those operations may create a duplicate; retry with the same event ID. The inbox
protects transactional database effects. Email, payment and delivery operations
still require their own idempotency/reconciliation mechanism. These are standard
queues; this procedure does not provide FIFO ordering or a cross-service replay.

## Verification evidence and limits

Verified on 15 October 2026 against running Floci 2.2.0 on localhost:4566:

```text
PASS: three handler failures, rollback after each, unchanged event in DLQ
PASS: replay preserves event_id, commits one effect and acknowledges the job
PASS: duplicate replay has no second effect; source queue and DLQ are empty
```

This checks real SQS-compatible redrive/acknowledgement and the M03 transaction
helper with an isolated SQLite effect. M03's existing PostgreSQL tests cover its
database implementation. EventBridge routing was verified by F12/M01/S05 and is
not repeated here. AWS redrive, IAM, encryption, alarms and real service/provider
side effects remain deployment/integration checks; no AWS compatibility claim is
made by this local probe. No shared queues, event contracts or migrations change.
