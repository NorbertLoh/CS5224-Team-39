"""Consume the fulfilment queue; acknowledge only after state and inbox commit."""

import argparse
from functools import partial

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.inbox import consume_batch
from telelink_common.logging import configure_logging

from app.database import create_database_engine
from app.integrations.billing import BillingClient
from app.models import event_inbox
from app.services.payments import confirm_payment
from app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Consume medication payment events")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    billing = None
    sqs = None
    try:
        billing = BillingClient(settings)
        sqs = create_client("sqs", settings)
        queue_url = sqs.get_queue_url(QueueName=settings.payment_queue_name)["QueueUrl"]
        sessions = sessionmaker(engine)
        while True:
            result = consume_batch(
                sessions,
                event_inbox,
                sqs,
                queue_url,
                "fulfilment",
                partial(confirm_payment, billing=billing),
                wait_seconds=5,  # SDK read timeout is 10s.
            )
            if args.once:
                print(result)
                return
    finally:
        if billing:
            billing.close()
        if sqs:
            sqs.close()
        engine.dispose()


if __name__ == "__main__":
    main()
