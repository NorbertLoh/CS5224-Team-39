"""S05 SQS consumer. Publishing is separate so queue polling never delays outbox retries."""

import argparse
import time
from functools import partial

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.inbox import consume_batch
from telelink_common.logging import configure_logging
from telelink_common.outbox import publish_pending

from app.billing import BillingClient
from app.database import create_database_engine
from app.models import event_inbox, event_outbox
from app.payment_recovery import deliver_resolutions
from app.payments import confirm_payment
from app.settings import Settings
from app.tenant import TenantClient


def main():
    parser = argparse.ArgumentParser(description="Consume payments or publish confirmations")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--resolve", action="store_true", help="Retry billing refund-required flags")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.publish and not settings.event_bus_name:
        parser.error("Publishing requires SERVICE_EVENT_BUS_NAME")
    configure_logging(settings.log_level)
    engine = create_database_engine(
        settings.database_url.get_secret_value() if settings.database_url else None
    )
    sessions = sessionmaker(engine)
    billing = None
    client = None
    tenant = None
    try:
        if args.publish:
            client = create_client("events", settings)
        else:
            billing = BillingClient(settings)
            if not args.resolve:
                if not settings.tenant_url or not settings.scheduling_secret:
                    parser.error("Payment recovery requires tenant_url and scheduling_secret")
                tenant = TenantClient(settings)
                client = create_client("sqs", settings)
                queue_url = client.get_queue_url(QueueName=settings.payment_queue_name)["QueueUrl"]
        while True:
            if args.publish:
                result = publish_pending(sessions, event_outbox, client, settings.event_bus_name)
            elif args.resolve:
                result = deliver_resolutions(sessions, billing)
            else:
                # M01's SDK read timeout is 10s: poll for 5s rather than M03's default 20s.
                result = consume_batch(
                    sessions,
                    event_inbox,
                    client,
                    queue_url,
                    "scheduling",
                    partial(confirm_payment, billing=billing, tenant=tenant),
                    wait_seconds=5,
                )
            if args.once:
                print(result)
                return
            if args.publish or args.resolve:
                time.sleep(1)
    finally:
        if billing:
            billing.close()
        if tenant:
            tenant.close()
        if client:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
