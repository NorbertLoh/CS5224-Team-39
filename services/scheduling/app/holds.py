"""PostgreSQL slot -> appointment lock order; Redis mirrors never allocate capacity."""

import logging
from datetime import datetime

import redis
from sqlalchemy import select, text

from app.models import Appointment

logger = logging.getLogger("telelink.scheduling.holds")
DELETE_OWN_HOLD = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


def server_now(session) -> datetime:
    # transaction_timestamp()/now() could predate a wait for the slot lock.
    return session.scalar(text("SELECT clock_timestamp()"))


class HoldCache:
    def __init__(self, settings):
        self.client = (
            redis.Redis.from_url(
                settings.redis_url.get_secret_value(),
                decode_responses=True,
                socket_connect_timeout=settings.redis_timeout_seconds,
                socket_timeout=settings.redis_timeout_seconds,
                retry_on_timeout=False,
            )
            if settings.redis_url
            else None
        )

    @staticmethod
    def key(slot_id):
        return f"telelink:scheduling:hold:{slot_id}"

    def close(self):
        if self.client is not None:
            self.client.close()

    def ready(self):
        try:
            return self.client is not None and bool(self.client.ping())
        except redis.RedisError:
            return False

    def mirror(self, appointment):
        if self.client is None:
            return
        try:
            self.client.set(
                self.key(appointment.slot_id),
                str(appointment.appointment_id),
                pxat=int(appointment.hold_expires_at.timestamp() * 1000),
            )
        except redis.RedisError:
            # The durable hold still succeeds. Log no patient IDs or credentials.
            logger.warning("hold_cache_unavailable")

    def release(self, slot_id, appointment_id):
        if self.client is None:
            return
        try:
            self.client.eval(DELETE_OWN_HOLD, 1, self.key(slot_id), str(appointment_id))
        except redis.RedisError:
            logger.warning("hold_cache_unavailable")


def expire_slot_holds(session, slot_id, now, cache):
    """Caller must own the slot row lock before locking any appointment rows."""
    expired = session.scalars(
        select(Appointment)
        .where(
            Appointment.slot_id == slot_id,
            Appointment.status.in_(("held", "pending_payment")),
            Appointment.hold_expires_at <= now,
        )
        .order_by(Appointment.appointment_id)
        .with_for_update()
    ).all()
    for appointment in expired:
        appointment.status = "expired"
        cache.release(slot_id, appointment.appointment_id)
    # Release uniqueness before an INSERT; ORM flush ordering otherwise inserts first.
    if expired:
        session.flush()
    return len(expired)
