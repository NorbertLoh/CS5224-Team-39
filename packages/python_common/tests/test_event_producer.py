from datetime import datetime, timedelta, timezone

import pytest
from event_fixtures import APPOINTMENT, CORRELATION, TENANT

from telelink_common.events import (
    AppointmentConfirmed,
    EventValidationError,
    PrescriptionIssued,
    new_event,
    parse_put_events_entry,
    to_put_events_entry,
)


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
