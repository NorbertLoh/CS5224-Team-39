"""M02 transactional outbox: stage events with domain changes, publish them with retries.

Consumer acknowledgement and inbox deduplication are M03.
"""

from telelink_common.outbox.publisher import (
    MAX_BATCH,
    PublishResult,
    add_event,
    publish_pending,
    retry_delay,
)
from telelink_common.outbox.table import outbox_table

__all__ = [
    "MAX_BATCH",
    "PublishResult",
    "add_event",
    "outbox_table",
    "publish_pending",
    "retry_delay",
]
