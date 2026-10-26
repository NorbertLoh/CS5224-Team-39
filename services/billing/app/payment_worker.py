"""Process verified Stripe receipts or independently publish their stored events."""

import argparse
import logging
import time

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.logging import configure_logging
from telelink_common.outbox import publish_pending

from app.api.refunds import process_refunds
from app.database import create_database_engine
from app.models import event_outbox
from app.payments import process_pending
from app.provider import StripeCheckout
from app.settings import Settings
from app.upstream import CheckoutSources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.publish and not settings.event_bus_name:
        parser.error("Publishing requires SERVICE_EVENT_BUS_NAME")
    if not args.publish and not settings.stripe_secret_key:
        parser.error("Processing requires SERVICE_STRIPE_SECRET_KEY")
    configure_logging(settings.log_level)
    engine = create_database_engine(
        settings.database_url.get_secret_value() if settings.database_url else None
    )
    provider = None
    client = None
    sources = None
    try:
        client = create_client("events", settings) if args.publish else None
        provider = None if args.publish else StripeCheckout(settings)
        sources = None if args.publish else CheckoutSources(settings)
        while True:
            try:
                result = (
                    publish_pending(
                        sessionmaker(engine), event_outbox, client, settings.event_bus_name
                    )
                    if args.publish
                    else process_pending(engine, provider)
                )
                if not args.publish:
                    result["refunds"] = process_refunds(engine, provider, sources)
            except SQLAlchemyError:
                # Transaction rolled back. Never log SQL parameters or provider bodies.
                logging.getLogger(__name__).error("payment_worker_storage_unavailable")
                if args.once:
                    raise SystemExit(1) from None
            else:
                if args.once:
                    print(result)
                    return
            time.sleep(1)
    finally:
        if provider:
            provider.close()
        if client:
            client.close()
        if sources:
            sources.close()
        engine.dispose()


if __name__ == "__main__":
    main()
