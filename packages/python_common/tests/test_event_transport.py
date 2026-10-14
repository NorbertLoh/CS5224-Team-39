import pytest
from event_fixtures import FIXTURES, sqs_body

from telelink_common.events import EventValidationError, parse_put_events_entry, parse_sqs_body


@pytest.mark.parametrize(
    "changes",
    [
        {"Source": "telelink.scheduling"},
        {"DetailType": "consultation_payment_succeeded.v2"},
        {"DetailType": None},
        {"Time": "2026-10-12T03:00:01.000Z"},
        {"Detail": {"already": "parsed"}},
        {"Detail": "not json"},
    ],
)
def test_entry_transport_fields_are_checked(changes):
    entry = {**FIXTURES[0], **changes}
    with pytest.raises(EventValidationError):
        parse_put_events_entry(entry)


@pytest.mark.parametrize(
    ("body", "consumer", "message"),
    [
        (sqs_body(FIXTURES[0]), "notification", "not routed"),
        (sqs_body(FIXTURES[0], source="telelink.document"), "scheduling", "source"),
        (sqs_body(FIXTURES[0], detail=FIXTURES[0]["Detail"]), "scheduling", "detail must"),
        ("not json", "scheduling", "JSON"),
        ("[]", "scheduling", "object"),
        (b"null", "scheduling", "object"),
    ],
)
def test_sqs_body_rejects_misrouted_and_malformed_messages(body, consumer, message):
    with pytest.raises(EventValidationError, match=message):
        parse_sqs_body(body, consumer=consumer)


def test_sqs_body_requires_a_known_consumer():
    body = sqs_body(FIXTURES[0])
    with pytest.raises(ValueError, match="unknown consumer"):
        parse_sqs_body(body, consumer="billing")
