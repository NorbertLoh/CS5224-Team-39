"""Opt-in CloudWatch Embedded Metric Format; no event contents or AWS API calls."""

import json
import os
import time

from sqlalchemy import func, select

_last_emitted = {}


def emit_backlog(session, outbox):
    if os.environ.get("SERVICE_OUTBOX_METRICS", "false").lower() != "true":
        return
    key = outbox.fullname
    tick = time.monotonic()
    if tick - _last_emitted.get(key, float("-inf")) < 60:
        return
    pending, oldest, now = session.execute(
        select(func.count(), func.min(outbox.c.created_at), func.current_timestamp())
        .select_from(outbox)
        .where(outbox.c.published_at.is_(None))
    ).one()
    age = max(0, (now - oldest).total_seconds()) if oldest else 0
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "TeleLink/Outbox",
                            "Dimensions": [["Service", "Environment"]],
                            "Metrics": [
                                {"Name": "PendingEvents", "Unit": "Count"},
                                {"Name": "OldestPendingAge", "Unit": "Seconds"},
                            ],
                        }
                    ],
                },
                "Service": outbox.schema,
                "Environment": os.environ.get("SERVICE_ENVIRONMENT", "local"),
                "PendingEvents": pending,
                "OldestPendingAge": age,
            }
        ),
        flush=True,
    )
    _last_emitted[key] = tick
