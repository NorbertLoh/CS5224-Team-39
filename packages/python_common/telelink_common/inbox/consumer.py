"""Receive events from a consumer queue, handle each once and acknowledge after commit."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Table, insert, select
from sqlalchemy.orm import Session, sessionmaker

from telelink_common.events import CONSUMERS, WorkflowEvent, parse_sqs_body

MAX_MESSAGES = 10  # ReceiveMessage returns at most 10 messages per call.

logger = logging.getLogger("telelink.inbox")

Handler = Callable[[Session, WorkflowEvent], None]


@dataclass(frozen=True)
class ConsumeResult:
    processed: int = 0
    duplicates: int = 0
    failed: int = 0


def handle_event(
    sessions: sessionmaker, inbox: Table, consumer: str, event: WorkflowEvent, handler: Handler
) -> bool:
    """Run the handler and record the inbox row in one transaction.

    Returns False without calling the handler when the event was already handled.
    A concurrent duplicate fails on the inbox primary key, rolls back and is
    retried later, when it is then seen as a duplicate.
    """
    with sessions.begin() as session:
        seen = session.scalar(
            select(inbox.c.event_id).where(
                inbox.c.consumer == consumer, inbox.c.event_id == event.event_id
            )
        )
        if seen is not None:
            return False
        session.execute(
            insert(inbox).values(
                consumer=consumer, event_id=event.event_id, detail_type=event.detail_type
            )
        )
        handler(session, event)
    return True


def consume_batch(
    sessions: sessionmaker,
    inbox: Table,
    sqs,
    queue_url: str,
    consumer: str,
    handler: Handler,
    *,
    max_messages: int = MAX_MESSAGES,
    wait_seconds: int = 20,
) -> ConsumeResult:
    """Receive one batch and delete each message only after it is handled.

    Failed or invalid messages are left on the queue: they reappear after the
    visibility timeout and move to the consumer DLQ after `maxReceiveCount`.
    """
    if consumer not in CONSUMERS:
        raise ValueError("unknown consumer")
    if not 1 <= max_messages <= MAX_MESSAGES:
        raise ValueError(f"max_messages must be between 1 and {MAX_MESSAGES}")
    messages = sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=max_messages, WaitTimeSeconds=wait_seconds
    ).get("Messages", [])
    processed = duplicates = failed = 0
    for message in messages:
        try:
            event = parse_sqs_body(message["Body"], consumer=consumer)
            handled = handle_event(sessions, inbox, consumer, event, handler)
        except Exception as error:
            # Type only: exception text can contain payload values.
            logger.warning("inbox_message_failed", exc_info=error)
            failed += 1
            continue
        if handled:
            processed += 1
        else:
            duplicates += 1
        try:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
        except Exception as error:
            # Already committed; the redelivered message is skipped as a duplicate.
            logger.warning("inbox_delete_failed", exc_info=error)
    return ConsumeResult(processed=processed, duplicates=duplicates, failed=failed)
