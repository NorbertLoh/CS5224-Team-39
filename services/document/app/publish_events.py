"""Publish committed document-ready outbox entries: python -m app.publish_events."""

import argparse
import time

from sqlalchemy.orm import sessionmaker
from telelink_common.aws import create_client
from telelink_common.outbox import publish_pending

from app.database import create_database_engine
from app.models import event_outbox
from app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = Settings()
    engine = create_database_engine(
        config.database_url.get_secret_value() if config.database_url else None
    )
    events = create_client("events", config)
    try:
        while True:
            result = publish_pending(
                sessionmaker(engine), event_outbox, events, config.event_bus_name
            )
            if args.once:
                print(result)
                return
            time.sleep(2)
    finally:
        events.close()
        engine.dispose()


if __name__ == "__main__":
    main()
