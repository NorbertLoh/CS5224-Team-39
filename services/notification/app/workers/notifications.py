"""Consume notification events and dispatch durable jobs.

CLI: python -m app.workers.notifications [--once].
"""

import argparse
import logging
from contextlib import ExitStack

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.inbox import consume_batch
from telelink_common.logging import configure_logging

from app.database import create_database_engine
from app.integrations.email import SESEmailSender
from app.integrations.recipients import RecipientDirectory
from app.models import event_inbox
from app.services.dispatch import dispatch_one, recover_stale
from app.services.intake import QueueNotification
from app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    for name in ("botocore", "boto3", "httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    with ExitStack() as stack:
        engine = create_database_engine(
            settings.database_url.get_secret_value() if settings.database_url else None
        )
        stack.callback(engine.dispose)
        directory = RecipientDirectory(settings)
        stack.callback(directory.close)
        sender = SESEmailSender(settings)
        stack.callback(sender.client.close)
        sqs = create_client("sqs", settings)
        stack.callback(sqs.close)
        queue_url = sqs.get_queue_url(QueueName=settings.queue_name)["QueueUrl"]
        sessions = sessionmaker(engine, expire_on_commit=False)
        handler = QueueNotification(directory)
        while True:
            recover_stale(sessions, settings)
            result = consume_batch(
                sessions,
                event_inbox,
                sqs,
                queue_url,
                "notification",
                handler,
                max_messages=10,
                wait_seconds=0 if args.once else 5,
            )
            sent = 0
            for _ in range(10):
                if not dispatch_one(sessions, sender, settings):
                    break
                sent += 1
            if args.once:
                print(
                    f"processed={result.processed} duplicates={result.duplicates} "
                    f"failed={result.failed} dispatched={sent}"
                )
                return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        configure_logging("ERROR")
        logging.getLogger(__name__).exception("notification_worker_failed")
        raise SystemExit(1) from None
