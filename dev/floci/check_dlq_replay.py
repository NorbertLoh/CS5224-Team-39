"""M04: exercise real local SQS redrive with the shared transactional consumer."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
from botocore.config import Config
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    create_engine,
    func,
    insert,
    select,
)
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/python_common"))


def verify(endpoint):
    target = urlsplit(endpoint)
    if target.scheme != "http" or target.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit(
            "Use a local Floci HTTP endpoint; this probe never targets AWS."
        )
    if target.username or target.password or target.query or target.fragment:
        raise SystemExit("Endpoint must not contain credentials, query or fragment.")
    sqs = boto3.client(
        "sqs",
        endpoint_url=endpoint,
        region_name="ap-southeast-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
    )
    suffix = uuid4().hex[:12]
    queues = []

    def create(name, attributes):
        url = sqs.create_queue(QueueName=name, Attributes=attributes)["QueueUrl"]
        # Floci queue URLs can contain a container-only hostname.
        url = endpoint.rstrip("/") + urlsplit(url).path
        queues.append(url)
        return url

    try:
        dlq = create(
            f"telelink-m04-{suffix}-dlq", {"MessageRetentionPeriod": "1209600"}
        )
        arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        queue = create(
            f"telelink-m04-{suffix}",
            {
                "VisibilityTimeout": "1",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": arn, "maxReceiveCount": 3}
                ),
            },
        )
        with TemporaryDirectory(prefix="telelink-m04-") as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'probe.sqlite'}")
            try:
                exercise(sqs, queue, dlq, engine)
            finally:
                engine.dispose()
    finally:
        # Only queues created by this run; never purge shared consumer queues.
        for url in reversed(queues):
            sqs.delete_queue(QueueUrl=url)


def exercise(sqs, queue, dlq, engine):
    from telelink_common.events import parse_sqs_body
    from telelink_common.inbox import ConsumeResult, consume_batch, inbox_table

    metadata = MetaData()
    inbox = inbox_table(metadata)
    effects = Table("probe_effects", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)
    sessions = sessionmaker(engine)
    entry = next(
        value
        for value in json.loads(
            (ROOT / "contracts/examples/workflow-events.json").read_text(
                encoding="utf-8"
            )
        )
        if value["DetailType"] == "appointment_confirmed.v1"
    )
    detail = json.loads(entry["Detail"])
    detail.update(event_id=str(uuid4()), correlation_id=str(uuid4()))
    body = json.dumps(
        {
            "source": entry["Source"],
            "detail-type": entry["DetailType"],
            "detail": detail,
        }
    )
    event = parse_sqs_body(body, consumer="notification")
    sqs.send_message(QueueUrl=queue, MessageBody=body)

    def count(table):
        with sessions() as session:
            return session.scalar(select(func.count()).select_from(table))

    def failing(session, event):
        session.execute(insert(effects).values(id=1))
        raise RuntimeError("synthetic M04 failure")

    failures = 0
    deadline = time.monotonic() + 45
    message = None
    while time.monotonic() < deadline:
        result = consume_batch(
            sessions,
            inbox,
            sqs,
            queue,
            "notification",
            failing,
            wait_seconds=1,
            max_messages=1,
        )
        failures += result.failed
        assert count(inbox) == count(effects) == 0, "Failed job committed state"
        messages = sqs.receive_message(QueueUrl=dlq, WaitTimeSeconds=1).get(
            "Messages", []
        )
        if messages:
            message = messages[0]
            break
    assert message is not None, "Failed job did not reach the DLQ within 45 seconds"
    assert failures == 3, f"Expected three failed receives, got {failures}"
    assert message["Body"] == body, "DLQ changed the event body"
    print("PASS: three handler failures, rollback after each, unchanged event in DLQ")

    # Operator replay: send the original body first; acknowledge DLQ only on success.
    sqs.send_message(QueueUrl=queue, MessageBody=message["Body"])
    sqs.delete_message(QueueUrl=dlq, ReceiptHandle=message["ReceiptHandle"])

    def repaired(session, received):
        assert received.event_id == event.event_id
        session.execute(insert(effects).values(id=1))

    result = consume_batch(
        sessions, inbox, sqs, queue, "notification", repaired, wait_seconds=1
    )
    assert result == ConsumeResult(processed=1)
    assert count(inbox) == count(effects) == 1
    print(
        "PASS: replay preserves event_id, commits one effect and acknowledges the job"
    )
    # A crash between send and delete can replay twice. The inbox must cover that gap.
    sqs.send_message(QueueUrl=queue, MessageBody=body)
    result = consume_batch(
        sessions, inbox, sqs, queue, "notification", repaired, wait_seconds=1
    )
    assert result == ConsumeResult(duplicates=1)
    assert count(inbox) == count(effects) == 1
    for url in (queue, dlq):
        assert not sqs.receive_message(QueueUrl=url, WaitTimeSeconds=1).get("Messages")
    print("PASS: duplicate replay has no second effect; source queue and DLQ are empty")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://localhost:4566")
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)  # Expected synthetic handler failures.
    verify(args.endpoint)
