"""Period classification and role-scoped pagination on real PostgreSQL."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from test_api import api as api
from test_api import api_database as api_database
from test_appointments import record


def read(api, period, *, role="patient", **params):
    return api[0].get("/appointments", headers=api[1](role), params={"period": period, **params})


def test_active_ongoing_ended_and_terminal_partition_including_expired_holds(api):
    now = datetime.now(timezone.utc)
    future = record(api, status="confirmed", start=now + timedelta(days=1))
    ongoing = record(api, status="in_progress", start=now - timedelta(minutes=10))
    ended = record(api, status="confirmed", start=now - timedelta(hours=1))
    completed = record(api, status="completed", start=now - timedelta(days=2))
    cancelled = record(api, status="cancelled", start=now + timedelta(days=2))
    expired_hold = record(api, expired=True)
    pending = record(api, status="pending_payment", start=now + timedelta(days=3))
    upcoming = read(api, "upcoming")
    past = read(api, "past")
    assert upcoming.status_code == past.status_code == 200
    assert [a["appointment_id"] for a in upcoming.json()["items"]] == [
        str(a.appointment_id) for a in (ongoing, future, pending)
    ]
    history = {a["appointment_id"]: a for a in past.json()["items"]}
    assert set(history) == {
        str(a.appointment_id) for a in (ended, completed, cancelled, expired_hold)
    }
    assert history[str(expired_hold.appointment_id)]["status"] == "expired"
    assert str(ongoing.appointment_id) not in history
    # Period filtering happens before page size, rather than splitting an oldest-first page.
    assert read(api, "upcoming", limit=1).json()["items"][0]["appointment_id"] == str(
        ongoing.appointment_id
    )


@pytest.mark.parametrize("period", ["upcoming", "past"])
@pytest.mark.parametrize("equal_times", [False, True])
def test_period_pagination_direction_ties_and_cursor_scope(api, period, equal_times):
    now = datetime.now(timezone.utc)
    base = now + timedelta(days=2) if period == "upcoming" else now - timedelta(days=2)
    items = [
        record(
            api,
            status="confirmed" if period == "upcoming" else "completed",
            doctor=uuid4(),
            start=base + timedelta(hours=0 if equal_times else i),
        )
        for i in range(3)
    ]
    expected = sorted(
        items, key=lambda a: (a.starts_at, str(a.appointment_id)), reverse=period == "past"
    )
    response = read(api, period, limit=1)
    assert response.status_code == 200, response.text
    page = response.json()
    first_cursor = page["next_cursor"]
    seen = [a["appointment_id"] for a in page["items"]]
    while page["next_cursor"]:
        response = read(api, period, limit=1, cursor=page["next_cursor"])
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(a["appointment_id"] for a in page["items"])
    assert seen == [str(a.appointment_id) for a in expected]
    assert len(set(seen)) == 3
    other = "past" if period == "upcoming" else "upcoming"
    assert read(api, other, cursor=first_cursor, limit=1).status_code == 422
    assert (
        api[0]
        .get("/appointments", headers=api[1]("patient"), params={"cursor": first_cursor})
        .status_code
        == 422
    )


@pytest.mark.parametrize("role", ["patient", "doctor", "admin"])
def test_periods_keep_patient_doctor_and_selected_clinic_scope(api, role):
    now = datetime.now(timezone.utc)
    upcoming = record(api, status="confirmed", start=now + timedelta(days=1))
    past = record(api, status="completed", start=now - timedelta(days=1))
    record(api, status="confirmed", tenant=api[3], doctor=uuid4(), start=now + timedelta(days=2))
    for period, wanted in (("upcoming", upcoming), ("past", past)):
        response = read(api, period, role=role, tenant_id=str(api[2]))
        assert response.status_code == 200, response.text
        assert [a["appointment_id"] for a in response.json()["items"]] == [
            str(wanted.appointment_id)
        ]
    if role != "patient":
        assert read(api, "upcoming", role=role, tenant_id=str(api[3])).status_code == 404
        api[6]["doctor" if role == "doctor" else "admin"][0]["status"] = "revoked"
        assert read(api, "past", role=role, tenant_id=str(api[2])).status_code == 403


def test_invalid_period_and_period_status_filters(api):
    record(api, status="confirmed")
    record(api, status="cancelled")
    assert read(api, "invalid").status_code == 422
    assert read(api, "upcoming", status="cancelled").json()["items"] == []
    past = read(api, "past", status="cancelled").json()["items"]
    assert len(past) == 1 and past[0]["status"] == "cancelled"
