"""Replay a committed fulfilment event through isolated local SQS queues.

Injects a post-commit acknowledgment failure; real Floci performs redrive. The
original event/inbox and historical submitted delivery must already exist.
"""

import argparse
import json
import logging
import sys
import time
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import boto3
import psycopg
from botocore.config import Config
from dotenv import dotenv_values
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from telelink_common.events import parse_sqs_body
from telelink_common.inbox import ConsumeResult, consume_batch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/fulfilment"))
from app.database import create_database_engine  # noqa: E402
from app.models import event_inbox  # noqa: E402
from app.services.deliveries import submit_delivery  # noqa: E402
from app.services.payments import confirm_payment  # noqa: E402
from app.settings import Settings  # noqa: E402


def check(name, passed):
    print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)
    if not passed:
        raise AssertionError(name)


class NoExternalCalls:
    """A duplicate must return before consulting billing or the courier."""

    def __getattr__(self, name):
        raise AssertionError("Replay attempted an external operation")


class WithholdAcknowledgment:
    """Controlled transport fault, with real receives and unchanged DB handling."""

    def __init__(self, sqs):
        self.sqs = sqs
        self.failures = 0

    def receive_message(self, **kwargs):
        return self.sqs.receive_message(**kwargs)

    def delete_message(self, **kwargs):
        self.failures += 1
        raise ConnectionError("Q03 controlled post-commit acknowledgment failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("order_id", type=UUID)
    parser.add_argument("--config-root", type=Path, default=ROOT)
    args = parser.parse_args()
    settings = Settings(_env_file=args.config_root / "services/fulfilment/.env")
    if settings.environment not in {
        "local",
        "test",
    } or settings.aws_endpoint_url not in {
        "http://localhost:4566",
        "http://127.0.0.1:4566",
    }:
        parser.error("Use local/test with host-local Floci on 4566")
    endpoint = settings.aws_endpoint_url
    logging.getLogger("telelink.inbox").addHandler(logging.NullHandler())
    logging.getLogger("telelink.inbox").propagate = False

    with ExitStack() as stack:

        def database(service):
            values = dotenv_values(args.config_root / f"services/{service}/.env")
            url = make_url(values["SERVICE_DATABASE_URL"])
            if (
                url.host not in {"localhost", "127.0.0.1"}
                or url.port != 55411
                or url.username != service
                or url.database != "telelink"
                or (
                    service == "fulfilment"
                    and make_url(settings.database_url.get_secret_value()) != url
                )
            ):
                parser.error(
                    "Use each service's own role on the persistent local database, 55411"
                )
            return stack.enter_context(
                psycopg.connect(
                    url.set(drivername="postgresql").render_as_string(
                        hide_password=False
                    ),
                    autocommit=True,
                    options="-c default_transaction_read_only=on",
                    row_factory=dict_row,
                )
            )

        fulfilment = database("fulfilment")
        billing = database("billing")

        def snapshot():
            order = fulfilment.execute(
                "SELECT to_jsonb(o) AS data FROM fulfilment.orders o WHERE order_id=%s",
                (args.order_id,),
            ).fetchone()
            deliveries = fulfilment.execute(
                "SELECT to_jsonb(d) AS data FROM fulfilment.deliveries d "
                "WHERE order_id=%s ORDER BY delivery_id",
                (args.order_id,),
            ).fetchall()
            outbox = fulfilment.execute(
                "SELECT to_jsonb(e) AS data FROM fulfilment.event_outbox e "
                "WHERE detail::jsonb->'data'->>'order_id'=%s ORDER BY event_id",
                (str(args.order_id),),
            ).fetchall()
            return order, deliveries, outbox

        before = snapshot()
        check("existing paid medication order", before[0] is not None)
        order = before[0]["data"]
        check("order retains succeeded payment", order["payment_status"] == "succeeded")
        check(
            "one previously submitted delivery with provider identity",
            len(before[1]) == 1
            and before[1][0]["data"]["delivery_id"] == order["delivery_id"]
            and before[1][0]["data"]["status"]
            in {"submitted", "picked_up", "delivered", "cancelled"}
            and bool(before[1][0]["data"]["send_started_at"])
            and bool(before[1][0]["data"]["provider_order_id"]),
        )
        rows = billing.execute(
            "SELECT source,detail_type,detail,published_at FROM billing.event_outbox "
            "WHERE detail_type='medication_payment_succeeded.v1' "
            "AND detail::jsonb->'data'->>'payment_id'=%s",
            (order["payment_id"],),
        ).fetchall()
        check("one published original medication payment event", len(rows) == 1)
        row = rows[0]
        check("source event was published", row["published_at"] is not None)
        body = json.dumps(
            {
                "source": row["source"],
                "detail-type": row["detail_type"],
                "detail": json.loads(row["detail"]),
            }
        )
        event = parse_sqs_body(body, consumer="fulfilment")
        check(
            "event matches the target order, payment and tenant",
            event.data.order_id == args.order_id
            and str(event.data.payment_id) == order["payment_id"]
            and str(event.tenant_id) == order["tenant_id"],
        )

        def inbox():
            return fulfilment.execute(
                "SELECT to_jsonb(i) AS data FROM fulfilment.event_inbox i "
                "WHERE consumer='fulfilment' AND event_id=%s",
                (event.event_id,),
            ).fetchall()

        original_inbox = inbox()
        check(
            "one original committed fulfilment inbox receipt", len(original_inbox) == 1
        )
        engine = create_database_engine(settings)
        stack.callback(engine.dispose)
        sessions = sessionmaker(engine)
        blocked = NoExternalCalls()
        handler = partial(confirm_payment, billing=blocked)
        sqs = boto3.client(
            "sqs",
            endpoint_url=endpoint,
            region_name=settings.aws_region,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=Config(
                connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}
            ),
        )
        stack.callback(sqs.close)
        suffix = uuid4().hex[:12]

        def create_queue(name, attributes):
            result = sqs.create_queue(QueueName=name, Attributes=attributes)
            url = endpoint + urlsplit(result["QueueUrl"]).path
            stack.callback(sqs.delete_queue, QueueUrl=url)
            return url

        dlq = create_queue(
            f"telelink-q03-{suffix}-dlq", {"MessageRetentionPeriod": "1209600"}
        )
        arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        queue = create_queue(
            f"telelink-q03-{suffix}",
            {
                "VisibilityTimeout": "1",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": arn, "maxReceiveCount": 3}
                ),
            },
        )
        sqs.send_message(QueueUrl=queue, MessageBody=body)
        fault = WithholdAcknowledgment(sqs)
        duplicate_receives = 0
        message = None
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = consume_batch(
                sessions,
                event_inbox,
                fault,
                queue,
                "fulfilment",
                handler,
                wait_seconds=1,
                max_messages=1,
            )
            if result.processed or result.failed:
                raise AssertionError(
                    "Committed replay unexpectedly ran or failed its handler"
                )
            duplicate_receives += result.duplicates
            messages = sqs.receive_message(QueueUrl=dlq, WaitTimeSeconds=1).get(
                "Messages", []
            )
            if messages:
                message = messages[0]
                break
        check(
            "three failed acknowledgments cause real DLQ movement",
            message is not None and fault.failures == duplicate_receives == 3,
        )
        check("DLQ preserves the exact event body", message["Body"] == body)
        check(
            "failed acknowledgments preserve domain and inbox",
            snapshot() == before and inbox() == original_inbox,
        )
        sqs.send_message(QueueUrl=queue, MessageBody=message["Body"])
        sqs.delete_message(QueueUrl=dlq, ReceiptHandle=message["ReceiptHandle"])
        for attempt in range(2):
            if attempt:
                sqs.send_message(QueueUrl=queue, MessageBody=body)
            result = consume_batch(
                sessions, event_inbox, sqs, queue, "fulfilment", handler, wait_seconds=1
            )
            check(
                "recovery and repeated replay are acknowledged duplicates",
                result == ConsumeResult(duplicates=1),
            )
        for _ in range(2):
            check(
                "delivery submission replay is a no-op",
                submit_delivery(sessions, UUID(order["delivery_id"]), blocked, blocked)
                is False,
            )
        check(
            "one delivery and original domain/inbox/outbox state remain",
            snapshot() == before and inbox() == original_inbox,
        )
        for queue_url in (queue, dlq):
            check(
                "probe queue drained",
                not sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=1).get(
                    "Messages"
                ),
            )
        print(
            "Q03 fulfilment replay passed; post-commit acknowledgment failure was injected."
        )


if __name__ == "__main__":
    main()
