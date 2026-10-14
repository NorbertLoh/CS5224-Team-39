"""EventBridge PutEvents entries and SQS message bodies to and from WorkflowEvent."""

import json
from collections.abc import Mapping

from pydantic import ValidationError

from telelink_common.events.envelope import WorkflowEvent, format_timestamp
from telelink_common.events.errors import EventValidationError, safe_error
from telelink_common.events.registry import CONSUMERS, EVENT_TYPES


def to_put_events_entry(event: WorkflowEvent, event_bus_name: str) -> dict:
    """Build one EventBridge PutEvents entry; Detail is serialized exactly once."""
    detail = event.detail()
    return {
        "EventBusName": event_bus_name,
        "Source": event.source,
        "DetailType": event.detail_type,
        "Time": detail["occurred_at"],
        "Detail": json.dumps(detail, separators=(",", ":")),
    }


def _parse(source, detail_type, detail, consumer: str | None) -> WorkflowEvent:
    spec = EVENT_TYPES.get(detail_type) if isinstance(detail_type, str) else None
    if spec is None:
        raise EventValidationError("unsupported event type")
    if source != spec.source:
        raise EventValidationError("event source does not match its type")
    if consumer is not None:
        if consumer not in CONSUMERS:
            raise ValueError("unknown consumer")
        if consumer not in spec.consumers:
            raise EventValidationError("event type is not routed to this consumer")
    if not isinstance(detail, Mapping):
        raise EventValidationError("event detail must be a JSON object")
    try:
        return WorkflowEvent.model_validate({**detail, "detail_type": detail_type})
    except ValidationError as error:
        raise safe_error("invalid event detail", error) from None


def parse_put_events_entry(entry: Mapping) -> WorkflowEvent:
    """Validate a producer PutEvents entry, such as the C05 fixtures."""
    try:
        detail = json.loads(entry["Detail"])
    except (KeyError, TypeError, ValueError):
        raise EventValidationError("Detail must be a JSON string") from None
    event = _parse(entry.get("Source"), entry.get("DetailType"), detail, None)
    if entry.get("Time") != format_timestamp(event.occurred_at):
        raise EventValidationError("Time must equal occurred_at")
    return event


def parse_sqs_body(body: str | bytes, *, consumer: str) -> WorkflowEvent:
    """Parse an SQS message body holding the full EventBridge event, once."""
    try:
        wrapper = json.loads(body)
    except (TypeError, ValueError):
        raise EventValidationError("message body must be JSON") from None
    if not isinstance(wrapper, Mapping):
        raise EventValidationError("message body must be an EventBridge event object")
    return _parse(
        wrapper.get("source"), wrapper.get("detail-type"), wrapper.get("detail"), consumer
    )
