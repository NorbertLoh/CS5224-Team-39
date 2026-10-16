"""Operator worker: one slot lock per transaction, skip locks held by API requests."""

import argparse
import time

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session
from telelink_common.logging import configure_logging

from app.database import create_database_engine
from app.holds import HoldCache, expire_slot_holds, server_now
from app.models import Appointment, AvailabilitySlot
from app.settings import Settings


def expire_batch(engine, cache, *, batch_size=100):
    expired_count = 0
    for _ in range(batch_size):
        with Session(engine) as session, session.begin():
            due = exists().where(
                Appointment.slot_id == AvailabilitySlot.slot_id,
                Appointment.status.in_(("held", "pending_payment")),
                Appointment.hold_expires_at <= func.clock_timestamp(),
            )
            slot_id = session.scalar(
                select(AvailabilitySlot.slot_id)
                .where(due)
                .order_by(AvailabilitySlot.slot_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if slot_id is None:
                break
            expired_count += expire_slot_holds(session, slot_id, server_now(session), cache)
    return expired_count


def main():
    parser = argparse.ArgumentParser(description="Expire persisted appointment holds")
    parser.add_argument("--once", action="store_true", help="Run one bounded batch and exit")
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(
        settings.database_url.get_secret_value() if settings.database_url else None
    )
    cache = HoldCache(settings)
    try:
        while True:
            count = expire_batch(engine, cache)
            if args.once:
                print(f"Expired {count} appointment holds.")
                return
            time.sleep(5)
    finally:
        cache.close()
        engine.dispose()


if __name__ == "__main__":
    main()
