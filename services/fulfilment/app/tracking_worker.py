"""One authenticated GET per tick; run one worker per sandbox provider account."""

import argparse
import time

from sqlalchemy.orm import sessionmaker
from telelink_common.logging import configure_logging

from app.database import create_database_engine
from app.delivery_orders import SandboxDeliveries
from app.settings import Settings
from app.tracking import poll_next


def main():
    parser = argparse.ArgumentParser(description="Poll verified provider delivery status")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    provider = None
    try:
        provider = SandboxDeliveries(settings)
        sessions = sessionmaker(engine, expire_on_commit=False)
        while True:
            result = poll_next(
                sessions, provider, interval_seconds=settings.delivery_poll_interval_seconds
            )
            if args.once:
                print({"tracking": result})
                return
            # Under 30 requests/minute per process, below the sandbox GET limit of
            # 50/minute. Per-delivery scheduling and failure backoff survive restarts.
            time.sleep(2)
    finally:
        if provider is not None:
            provider.close()
        engine.dispose()


if __name__ == "__main__":
    main()
