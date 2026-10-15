"""Publish committed prescription events through the shared M02 retrying publisher."""

import argparse
import time

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.logging import configure_logging
from telelink_common.outbox import publish_pending

from app.database import create_database_engine
from app.models import event_outbox
from app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Publish pending prescription issuance events")
    parser.add_argument("--once", action="store_true", help="Publish one due batch, then exit")
    args = parser.parse_args()
    settings = Settings()
    if not settings.database_url or not settings.event_bus_name:
        parser.error("Publishing requires SERVICE_DATABASE_URL and SERVICE_EVENT_BUS_NAME")
    configure_logging(settings.log_level)
    engine = create_database_engine(
        settings.database_url.get_secret_value(), timeout_seconds=settings.database_timeout_seconds
    )
    client = None
    try:
        client = create_client("events", settings)
        sessions = sessionmaker(engine)
        while True:
            result = publish_pending(sessions, event_outbox, client, settings.event_bus_name)
            if args.once:
                print(result)
                return
            time.sleep(1)
    finally:
        if client is not None:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
