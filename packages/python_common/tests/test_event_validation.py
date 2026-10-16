import json

import pytest
from event_fixtures import APPOINTMENT, FIXTURES, TENANT, with_detail

from telelink_common.events import EventValidationError, parse_put_events_entry


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"schema_version": "1"},
        {"schema_version": True},
        {"event_id": "not-a-uuid"},
        {"tenant_id": None},
        {"correlation_id": ""},
        {"occurred_at": "2026-10-12T03:00:00Z"},
        {"occurred_at": "2026-10-12T11:00:00.000+08:00"},
        {"data": {}},
        {"data": "x"},
    ],
)
def test_malformed_detail_is_rejected(changes):
    entry = with_detail(FIXTURES[0], **changes)
    with pytest.raises(EventValidationError):
        parse_put_events_entry(entry)


@pytest.mark.parametrize(
    "data",
    [
        {"payment_id": "x", "appointment_id": APPOINTMENT, "amount": {"amount_minor": 1}},
        {"payment_id": TENANT, "appointment_id": APPOINTMENT},
        {
            "payment_id": TENANT,
            "appointment_id": APPOINTMENT,
            "amount": {"amount_minor": 25.0, "currency": "SGD"},
        },
        {
            "payment_id": TENANT,
            "appointment_id": APPOINTMENT,
            "amount": {"amount_minor": 2500, "currency": "sgd"},
        },
    ],
)
def test_required_data_fields_and_money_are_validated(data):
    entry = with_detail(FIXTURES[0], data=data)
    with pytest.raises(EventValidationError):
        parse_put_events_entry(entry)


def test_blank_delivery_status_is_rejected():
    entry = next(item for item in FIXTURES if item["DetailType"] == "delivery_status_changed.v1")
    data = json.loads(entry["Detail"])["data"]
    entry = with_detail(entry, data={**data, "status": "  "})
    with pytest.raises(EventValidationError):
        parse_put_events_entry(entry)


def test_unknown_optional_fields_are_ignored():
    detail = json.loads(FIXTURES[2]["Detail"])
    entry = with_detail(FIXTURES[2], extra_envelope="ok", data={**detail["data"], "added_later": 1})
    event = parse_put_events_entry(entry)
    assert event.detail()["data"] == {"appointment_id": APPOINTMENT}


def test_errors_do_not_echo_payload_values():
    secret = "patient@example.com"
    entry = with_detail(FIXTURES[0], tenant_id=secret)
    with pytest.raises(EventValidationError) as error:
        parse_put_events_entry(entry)
    assert secret not in str(error.value)
    assert "tenant_id" in str(error.value)
