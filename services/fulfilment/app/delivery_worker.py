"""Submission, outbox publishing and manual verified reconciliation entry points."""

import argparse
import logging
import time
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.logging import configure_logging
from telelink_common.outbox import publish_pending

from app.api.deliveries import (
    claim_deliveries,
    deliver_resolutions,
    locked,
    reconcile,
    submit_delivery,
    utcnow,
)
from app.billing import BillingClient
from app.database import create_database_engine
from app.delivery_orders import SandboxDeliveries
from app.models import Delivery, event_outbox
from app.settings import Settings

logger = logging.getLogger("telelink.delivery")


def submit_pending(sessions, provider, billing):
    claimed = claim_deliveries(sessions)
    with sessions() as session:
        ids = session.scalars(
            select(Delivery.delivery_id)
            .where(
                Delivery.status == "pending",
                Delivery.send_started_at.is_(None),
                Delivery.next_attempt_at <= utcnow(),
            )
            .order_by(Delivery.created_at)
            .limit(10)
        ).all()
    failed = 0
    for delivery_id in ids:
        try:
            submit_delivery(sessions, delivery_id, provider, billing)
        except Exception as error:
            # Before-send failures retry with backoff; unknown intents never resend.
            with sessions.begin() as session:
                _, delivery = locked(session, delivery_id)
                if delivery.status == "pending" and delivery.send_started_at is None:
                    delivery.attempts += 1
                    delivery.next_attempt_at = utcnow() + timedelta(
                        seconds=min(300, 5 * 2 ** min(delivery.attempts, 6))
                    )
                    delivery.failure_code = "preparation_unavailable"
            logger.warning("delivery_attempt_failed", exc_info=error)
            failed += 1
    return {"claimed": len(claimed), "checked": len(ids), "errors": failed}


def main():
    parser = argparse.ArgumentParser(description="Submit paid and ready deliveries")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--resolve", action="store_true")
    mode.add_argument("--reconcile", type=UUID, metavar="DELIVERY_UUID")
    parser.add_argument("--provider-order-id")
    parser.add_argument("--operator")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.reconcile and (not args.provider_order_id or not args.operator):
        parser.error("Reconciliation requires --provider-order-id and --operator")
    if not args.reconcile and (args.provider_order_id or args.operator):
        parser.error("Provider reference and operator are only used with --reconcile")
    settings = Settings()
    if args.publish and not settings.event_bus_name:
        parser.error("Publishing requires SERVICE_EVENT_BUS_NAME")
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    sessions = sessionmaker(engine, expire_on_commit=False)
    billing = provider = events = None
    try:
        if args.publish:
            events = create_client("events", settings)
        else:
            if not args.reconcile:
                billing = BillingClient(settings)
            if not args.resolve:
                provider = SandboxDeliveries(settings)
        while True:
            if args.publish:
                result = publish_pending(sessions, event_outbox, events, settings.event_bus_name)
            elif args.resolve:
                result = {"resolutions_delivered": deliver_resolutions(sessions, billing)}
            elif args.reconcile:
                result = {
                    "reconciled": reconcile(
                        sessions, args.reconcile, args.provider_order_id, provider, args.operator
                    )
                }
            else:
                result = submit_pending(sessions, provider, billing)
            if args.once or args.reconcile:
                print(result)
                return
            time.sleep(1)
    finally:
        for client in (billing, provider, events):
            if client is not None:
                client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
