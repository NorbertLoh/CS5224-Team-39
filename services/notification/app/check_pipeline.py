"""Verify synthetic owner-API -> EventBridge/SQS -> SES flow using isolated local resources."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.events import new_event
from telelink_common.inbox import consume_batch
from telelink_common.logging import configure_logging

from app.database import create_database_engine
from app.dispatch import dispatch_one
from app.email import SESEmailSender
from app.intake import QueueNotification
from app.models import NotificationJob, event_inbox
from app.recipients import RecipientDirectory
from app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture", type=Path, help="Synthetic resource IDs from isolated owner databases"
    )
    args = parser.parse_args()
    settings = Settings()
    configure_logging("WARNING")
    if settings.environment not in {"local", "test"} or settings.aws_endpoint_url not in {
        "http://localhost:4566",
        "http://127.0.0.1:4566",
    }:
        raise ValueError("Only local Floci on port 4566 is allowed")
    for name in ("identity", "scheduling", "document", "fulfilment"):
        if urlsplit(getattr(settings, name + "_url") or "").hostname not in {
            "localhost",
            "127.0.0.1",
        }:
            raise ValueError("Only host-local owner services are allowed")
    engine = create_database_engine(
        settings.database_url.get_secret_value() if settings.database_url else None
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    directory = RecipientDirectory(settings)
    sender = SESEmailSender(settings)
    sqs, events = create_client("sqs", settings), create_client("events", settings)
    suffix = uuid4().hex[:16]
    name = "n02-check-" + suffix
    queue_url = None
    bus_created = rule_created = False
    try:
        with sessions() as session:
            if session.scalar(select(func.count()).select_from(NotificationJob)) or session.scalar(
                select(func.count()).select_from(event_inbox)
            ):
                raise ValueError("Use an empty isolated notification database for this check")
        ids = json.loads(args.fixture.read_text())
        payloads = [
            ("appointment_confirmed.v1", {"appointment_id": ids["appointment_id"]}),
            (
                "document_ready.v1",
                {
                    "document_id": ids["document_id"],
                    "appointment_id": ids["appointment_id"],
                    "prescription_id": ids["prescription_id"],
                },
            ),
            (
                "document_ready.v1",
                {
                    "document_id": ids["mc_document_id"],
                    "appointment_id": ids["appointment_id"],
                    "medical_certificate_id": ids["medical_certificate_id"],
                },
            ),
            (
                "delivery_status_changed.v1",
                {
                    "delivery_id": ids["delivery_id"],
                    "order_id": ids["order_id"],
                    "status": "submitted",
                },
            ),
        ]
        workflow = [
            new_event(
                kind,
                tenant_id=ids["tenant_id"],
                correlation_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                data=data,
            )
            for kind, data in payloads
        ]
        queue_url = sqs.create_queue(QueueName=name)["QueueUrl"]
        queue_arn = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        events.create_event_bus(Name=name)
        bus_created = True
        rule = events.put_rule(
            Name=name,
            EventBusName=name,
            EventPattern=json.dumps(
                {"source": ["telelink.scheduling", "telelink.document", "telelink.fulfilment"]}
            ),
        )
        rule_created = True
        sqs.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "events.amazonaws.com"},
                                "Action": "sqs:SendMessage",
                                "Resource": queue_arn,
                                "Condition": {"ArnEquals": {"aws:SourceArn": rule["RuleArn"]}},
                            }
                        ],
                    }
                )
            },
        )
        assert (
            events.put_targets(
                Rule=name, EventBusName=name, Targets=[{"Id": "notification", "Arn": queue_arn}]
            )["FailedEntryCount"]
            == 0
        )
        entries = [
            {
                "EventBusName": name,
                "Source": value.source,
                "DetailType": value.detail_type,
                "Detail": json.dumps(value.detail()),
            }
            for value in workflow
        ]
        assert events.put_events(Entries=entries + entries)["FailedEntryCount"] == 0
        processed = duplicates = 0
        for _ in range(12):
            result = consume_batch(
                sessions,
                event_inbox,
                sqs,
                queue_url,
                "notification",
                QueueNotification(directory),
                wait_seconds=1,
            )
            assert result.failed == 0
            processed += result.processed
            duplicates += result.duplicates
            if processed == 4 and duplicates == 4:
                break
        assert (processed, duplicates) == (4, 4)
        # Explicit local guard: this verification can never address a real mailbox.
        with sessions() as session:
            jobs = list(session.scalars(select(NotificationJob)))
            assert len(jobs) == 4 and all(
                row.recipient_email.endswith("@telelink.test") for row in jobs
            )
        sender.client.verify_email_identity(EmailAddress=settings.email_sender)
        for email in {row.recipient_email for row in jobs}:
            sender.client.verify_email_identity(EmailAddress=email)
        for _ in jobs:
            assert dispatch_one(sessions, sender, settings)
        # New session factory simulates sender restart; no accepted job can be sent twice.
        assert not dispatch_one(sessionmaker(engine), sender, settings)
        from urllib.request import urlopen

        with urlopen(settings.aws_endpoint_url + "/_aws/ses", timeout=10) as response:
            captured = json.load(response)["messages"]
        with sessions() as session:
            jobs = list(session.scalars(select(NotificationJob)))
            accepted = {row.provider_message_id for row in jobs}
            assert len(accepted) == 4 and all(
                row.status == "sent" and row.attempts == 1 for row in jobs
            )
            assert sum(message["Id"] in accepted for message in captured) == 4
        print(
            "N02 pipeline passed: four events, four duplicates, four captured emails; "
            "restart did not resend."
        )
    finally:
        directory.close()
        sender.client.close()
        if rule_created:
            events.remove_targets(Rule=name, EventBusName=name, Ids=["notification"])
            events.delete_rule(Name=name, EventBusName=name)
        if bus_created:
            events.delete_event_bus(Name=name)
        if queue_url:
            sqs.delete_queue(QueueUrl=queue_url)
        events.close()
        sqs.close()
        engine.dispose()


if __name__ == "__main__":
    main()
