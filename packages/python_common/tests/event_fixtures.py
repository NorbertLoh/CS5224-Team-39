"""Shared C05 fixtures and builders for the event tests."""

import json
from pathlib import Path

from telelink_common.events import EVENT_TYPES

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT / "contracts/examples/workflow-events.json").read_text("utf-8"))
TENANT = "00000000-0000-4000-8000-000000000002"
CORRELATION = "00000000-0000-4000-8000-000000000001"
APPOINTMENT = "00000000-0000-4000-8000-000000000010"


def sqs_body(entry, **changes):
    """The full EventBridge wrapper SQS receives, without an input transformer."""
    wrapper = {
        "version": "0",
        "id": "transport-id",
        "detail-type": entry["DetailType"],
        "source": entry["Source"],
        "account": "000000000000",
        "time": "2026-10-12T03:00:00Z",
        "region": "ap-southeast-1",
        "resources": [],
        "detail": json.loads(entry["Detail"]),
    }
    wrapper.update(changes)
    return json.dumps(wrapper)


def consumer_for(entry):
    return next(iter(EVENT_TYPES[entry["DetailType"]].consumers))


def with_detail(entry, **changes):
    detail = {**json.loads(entry["Detail"]), **changes}
    return {**entry, "Detail": json.dumps(detail)}
