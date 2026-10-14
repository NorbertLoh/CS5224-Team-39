import json

import pytest
from event_fixtures import FIXTURES, ROOT, consumer_for, sqs_body

from telelink_common.events import (
    EVENT_TYPES,
    parse_put_events_entry,
    parse_sqs_body,
    to_put_events_entry,
)


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
