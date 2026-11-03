from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_api import api as api
from test_api import api_database as api_database
from test_appointments import record

from app.models import Appointment


@pytest.mark.parametrize("role", ["patient", "doctor", "admin"])
def test_search_and_effective_period_counts_share_role_and_clinic_scope(api, role):
    now = datetime.now(timezone.utc)
    future = record(api, status="confirmed", start=now + timedelta(days=1))
    past = record(api, status="completed", start=now - timedelta(days=1))
    expired = record(api, expired=True)
    hidden = record(
        api,
        status="confirmed",
        patient=api[4]["other_patient"],
        doctor=api[4]["other_doctor"],
        start=now + timedelta(days=3),
    )
    foreign = record(
        api, status="confirmed", tenant=api[3], doctor=uuid4(), start=now + timedelta(days=4)
    )
    with Session(api[-1]) as session, session.begin():
        for row in (future, past, expired, hidden, foreign):
            session.get(Appointment, row.appointment_id).patient_name = "Match 50% Person"
    params = {"tenant_id": str(api[2]), "q": " MATCH 50% "}
    client, auth = api[0], api[1](role)
    counts = client.get("/appointment-counts", params=params, headers=auth)
    assert counts.status_code == 200
    expected_total = 4 if role == "admin" else 3
    assert counts.json() == {"total": expected_total, "upcoming": expected_total - 2, "past": 2}
    for period in ("upcoming", "past"):
        listed = client.get("/appointments", params=params | {"period": period}, headers=auth)
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == counts.json()[period]
    assert (
        client.get(
            "/appointment-counts", params=params | {"status": "expired"}, headers=auth
        ).json()["past"]
        == 1
    )
    assert (
        client.get("/appointment-counts", params=params | {"q": "missing"}, headers=auth).json()[
            "total"
        ]
        == 0
    )
    if role != "patient":
        assert (
            client.get(
                "/appointment-counts", params=params | {"tenant_id": str(api[3])}, headers=auth
            ).status_code
            == 404
        )
        api[6]["doctor" if role == "doctor" else "admin"][0]["status"] = "revoked"
        assert client.get("/appointment-counts", params=params, headers=auth).status_code == 403


def test_appointment_counts_cover_all_pages_dates_and_search_bound_cursors(api):
    base = datetime.now(timezone.utc) + timedelta(days=2)
    for i in range(27):
        row = record(api, status="confirmed", start=base + timedelta(hours=i))
        with Session(api[-1]) as session, session.begin():
            session.get(Appointment, row.appointment_id).clinic_name = "Search clinic"
    params = {"q": "search", "from": base.isoformat(), "to": (base + timedelta(days=2)).isoformat()}
    client, auth = api[0], api[1]("patient")
    assert client.get("/appointment-counts", params=params, headers=auth).json()["total"] == 27
    first = client.get(
        "/appointments", params=params | {"limit": 25, "period": "upcoming"}, headers=auth
    ).json()
    assert len(first["items"]) == 25 and first["next_cursor"]
    assert (
        client.get(
            "/appointments",
            params=params | {"cursor": first["next_cursor"], "period": "upcoming", "q": "another"},
            headers=auth,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/appointment-counts", params={"q": "search", "to": base.isoformat()}, headers=auth
        ).json()["total"]
        == 0
    )
    assert client.get("/appointment-counts", params={"q": "%"}, headers=auth).json()["total"] == 0


def test_counts_and_lists_use_selected_workspace_for_multi_role_accounts(api):
    api[5]["roles"]["doctor"] = ["patient"]
    record(api, status="confirmed")
    own_patient = record(
        api, status="confirmed", patient=api[4]["doctor"], doctor=api[4]["other_doctor"]
    )
    client, auth = api[0], api[1]("doctor")
    for role in ("patient", "doctor"):
        params = {"view_role": role}
        count = client.get("/appointment-counts", params=params, headers=auth)
        assert count.status_code == 200 and count.json()["total"] == 1
        rows = client.get("/appointments", params=params, headers=auth).json()["items"]
        assert len(rows) == 1
        assert (rows[0]["appointment_id"] == str(own_patient.appointment_id)) == (role == "patient")
    assert (
        client.get(
            "/appointment-counts", params={"view_role": "clinic_admin"}, headers=auth
        ).status_code
        == 403
    )
