"""Stage events with their domain change, then publish due events with retries."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Table, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from telelink_common.events import WorkflowEvent
from telelink_common.outbox.metrics import emit_backlog

MAX_BATCH = 10  # PutEvents accepts at most 10 entries per call.
MAX_RETRY_DELAY = timedelta(minutes=5)

logger = logging.getLogger("telelink.outbox")


@dataclass(frozen=True)
class PublishResult:
    published: int = 0
    failed: int = 0


def add_event(session: Session, outbox: Table, event: WorkflowEvent) -> None:
    """Stage an event in the caller's transaction, so it commits or rolls back with it."""
    detail = event.detail()
    session.execute(
        insert(outbox).values(
            event_id=event.event_id,
            source=event.source,
            detail_type=event.detail_type,
            event_time=detail["occurred_at"],
            detail=json.dumps(detail, separators=(",", ":")),
        )
    )


def retry_delay(attempts: int) -> timedelta:
    """5s, 10s, 20s ... capped at five minutes."""
    return min(timedelta(seconds=5 * 2 ** min(attempts - 1, 6)), MAX_RETRY_DELAY)


def publish_pending(
    sessions: sessionmaker,
    outbox: Table,
    client,
    event_bus_name: str,
    *,
    batch_size: int = MAX_BATCH,
    now: datetime | None = None,
) -> PublishResult:
    """Send one batch of due events and record each entry's outcome.

    Rows stay locked until the outcome is saved, so concurrent publishers skip them.
    Failed entries keep their stored envelope and are retried later; successful
    siblings are not resent.
    """
    if not event_bus_name:
        raise ValueError("SERVICE_EVENT_BUS_NAME is required to publish events")
    if not 1 <= batch_size <= MAX_BATCH:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH}")
    now = now or datetime.now(timezone.utc)
    with sessions.begin() as session:
        emit_backlog(session, outbox)
        rows = session.execute(
            select(outbox)
            .where(outbox.c.published_at.is_(None), outbox.c.next_attempt_at <= now)
            .order_by(outbox.c.next_attempt_at, outbox.c.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        if not rows:
            return PublishResult()
        errors = _put_events(client, event_bus_name, rows)
        for row, error in zip(rows, errors):
            _record_outcome(session, outbox, row, error, now)
    failed = sum(error is not None for error in errors)
    return PublishResult(published=len(rows) - failed, failed=failed)


def _put_events(client, event_bus_name: str, rows) -> list[str | None]:
    """Return one error code per row, or None where EventBridge accepted it."""
    entries = [
        {
            "EventBusName": event_bus_name,
            "Source": row.source,
            "DetailType": row.detail_type,
            "Time": row.event_time,
            "Detail": row.detail,
        }
        for row in rows
    ]
    try:
        results = client.put_events(Entries=entries)["Entries"]
    except Exception as error:
        logger.warning("outbox_publish_failed", exc_info=error)
        return [type(error).__name__] * len(rows)
    if len(results) != len(rows):
        logger.warning("outbox_publish_invalid_response")
        return ["InvalidResponse"] * len(rows)
    # Store the error code only; EventBridge error messages can repeat entry content.
    return [result.get("ErrorCode") for result in results]


def _record_outcome(session: Session, outbox: Table, row, error: str | None, now: datetime):
    if error is None:
        values = {"published_at": now, "last_error": None}
    else:
        attempts = row.attempts + 1
        values = {
            "attempts": attempts,
            "last_error": str(error)[:100],
            "next_attempt_at": now + retry_delay(attempts),
        }
    session.execute(update(outbox).where(outbox.c.event_id == row.event_id).values(**values))
