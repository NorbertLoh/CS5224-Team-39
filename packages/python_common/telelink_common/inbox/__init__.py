"""M03 consumer inbox: handle each event once and acknowledge SQS messages after commit.

DLQ inspection and operator replay are M04.
"""

from telelink_common.inbox.consumer import (
    MAX_MESSAGES,
    ConsumeResult,
    Handler,
    consume_batch,
    handle_event,
)
from telelink_common.inbox.table import inbox_table

__all__ = [
    "MAX_MESSAGES",
    "ConsumeResult",
    "Handler",
    "consume_batch",
    "handle_event",
    "inbox_table",
]
