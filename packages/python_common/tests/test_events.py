import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from telelink_common.aws import client_options
from telelink_common.events import (
    EVENT_TYPES,
    AppointmentConfirmed,
    EventValidationError,
    PrescriptionIssued,
    new_event,
    parse_put_events_entry,
    parse_sqs_body,
    to_put_events_entry,
)
from telelink_common.settings import ServiceSettings

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


@pytest.mark.parametrize("entry", FIXTURES, ids=lambda entry: entry["DetailType"])
def test_contract_fixtures_validate_and_round_trip(entry):
    event = parse_put_events_entry(entry)
    built = to_put_events_entry(event, entry["EventBusName"])
    assert json.loads(built.pop("Detail")) == json.loads(entry["Detail"])
    assert built == {key: value for key, value in entry.items() if key != "Detail"}
    assert parse_sqs_body(sqs_body(entry), consumer=consumer_for(entry)) == event


def test_registry_matches_contract_fixtures_and_f12_routing():
    assert {entry["DetailType"] for entry in FIXTURES} == set(EVENT_TYPES)
    routed = set()
    for path in (ROOT / "dev/floci/patterns").glob("*.json"):
        pattern = json.loads(path.read_text("utf-8"))
        for rule in pattern.get("$or", [pattern]):
            routed |= {
                (path.stem, source, detail_type)
                for source in rule["source"]
                for detail_type in rule["detail-type"]
            }
    assert routed == {
        (consumer, spec.source, spec.detail_type)
        for spec in EVENT_TYPES.values()
        for consumer in spec.consumers
    }


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


def test_errors_do_not_echo_payload_values():
    secret = "patient@example.com"
    entry = with_detail(FIXTURES[0], tenant_id=secret)
    with pytest.raises(EventValidationError) as error:
        parse_put_events_entry(entry)
    assert secret not in str(error.value)
    assert "tenant_id" in str(error.value)


def test_new_event_normalizes_time_and_preserves_ids():
    occurred = datetime(2026, 10, 12, 11, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
    event = new_event(
        "appointment_confirmed.v1",
        tenant_id=TENANT,
        correlation_id=CORRELATION,
        occurred_at=occurred,
        data=AppointmentConfirmed(appointment_id=APPOINTMENT),
    )
    entry = to_put_events_entry(event, "telelink-local")
    assert entry["Time"] == "2026-10-12T03:00:00.123Z"
    assert entry["Source"] == "telelink.scheduling"
    assert parse_put_events_entry(entry) == event
    replay = new_event(
        "appointment_confirmed.v1",
        tenant_id=TENANT,
        correlation_id=CORRELATION,
        occurred_at=occurred,
        data={"appointment_id": APPOINTMENT},
        event_id=event.event_id,
    )
    assert to_put_events_entry(replay, "telelink-local") == entry


@pytest.mark.parametrize(
    "changes",
    [
        {"occurred_at": datetime(2026, 10, 12, 3)},
        {"detail_type": "appointment_cancelled.v1"},
        {"data": PrescriptionIssued(prescription_id=TENANT, appointment_id=APPOINTMENT)},
    ],
)
def test_new_event_rejects_invalid_input(changes):
    values = {
        "detail_type": "appointment_confirmed.v1",
        "tenant_id": TENANT,
        "correlation_id": CORRELATION,
        "occurred_at": datetime(2026, 10, 12, 3, tzinfo=timezone.utc),
        "data": {"appointment_id": APPOINTMENT},
        **changes,
    }
    detail_type = values.pop("detail_type")
    with pytest.raises(EventValidationError):
        new_event(detail_type, **values)


def test_sdk_settings_allow_emulator_endpoint_only_locally():
    local = ServiceSettings(
        _env_file=None,
        environment="local",
        aws_endpoint_url="http://floci:4566/",
        event_bus_name="telelink-local",
    )
    assert client_options(local) == {
        "region_name": "ap-southeast-1",
        "endpoint_url": "http://floci:4566",
    }
    deployed = ServiceSettings(_env_file=None, environment="development", aws_region="us-east-1")
    assert client_options(deployed) == {"region_name": "us-east-1"}
    for values in (
        {"environment": "production", "aws_endpoint_url": "http://localhost:4566"},
        {"environment": "local", "aws_endpoint_url": "https://events.example.com"},
        {"environment": "local", "aws_endpoint_url": "http://user:pw@localhost:4566"},
        {"environment": "local", "aws_endpoint_url": "http://localhost:4566/path"},
        {"aws_region": "Singapore"},
        {"event_bus_name": "bad bus"},
    ):
        with pytest.raises(ValidationError):
            ServiceSettings(_env_file=None, **values)
