import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from uuid import UUID, uuid4

import jwt
import pytest
import test_api
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app import appointments
from app.main import create_app
from app.models import Appointment, AvailabilitySlot
from app.settings import Settings

api = test_api.api
api_database = test_api.api_database
CONSULTATION = "s04-consultation-test-key-at-least-32-bytes"
OPERATOR = "s04-operator-test-key-at-least-32-bytes"


@pytest.fixture
def appointment_api(api):
    api[0].app.state.settings.consultation_secret = SecretStr(CONSULTATION)
    api[0].app.state.settings.operator_secret = SecretStr(OPERATOR)
    return api


def record(
    api, *, status="held", tenant=None, patient=None, doctor=None, start=None, expired=False
):
    now = datetime.now(timezone.utc)
    sequence = api[5].get("record_sequence", 0)
    api[5]["record_sequence"] = sequence + 1
    start = start or now + timedelta(days=1, hours=sequence)
    tenant, patient, doctor = (
        tenant or api[2],
        patient or api[4]["patient"],
        doctor or api[4]["doctor"],
    )
    with Session(api[-1], expire_on_commit=False) as session, session.begin():
        slot = AvailabilitySlot(
            tenant_id=tenant,
            doctor_id=doctor,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
        )
        session.add(slot)
        session.flush()
        hold_state = status in {"held", "pending_payment", "expired"}
        expires = (
            now - timedelta(minutes=1)
            if expired or status == "expired"
            else now + timedelta(minutes=5)
        )
        stored = Appointment(
            slot_id=slot.slot_id,
            tenant_id=tenant,
            patient_id=patient,
            doctor_id=doctor,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            status=status,
            hold_expires_at=expires if hold_state else None,
            consultation_price_minor=3210,
            payment_id=uuid4()
            if status in {"pending_payment", "confirmed", "in_progress", "completed", "no_show"}
            else None,
            payment_resolution="confirmed"
            if status in {"confirmed", "in_progress", "completed", "no_show"}
            else "awaiting_payment"
            if status == "pending_payment"
            else "none",
            created_at=now - timedelta(minutes=5) if expired or status == "expired" else now,
            updated_at=now,
        )
        session.add(stored)
        session.flush()
        return stored


def service(caller="consultation", **changes):
    now = int(time.time())
    audience = (
        "telelink-scheduling-consultation"
        if caller == "consultation"
        else "telelink-scheduling-operator"
    )
    token = jwt.encode(
        {
            "iss": "telelink-service:" + caller,
            "aud": audience,
            "sub": caller,
            "iat": now,
            "exp": now + 60,
        }
        | changes,
        CONSULTATION if caller == "consultation" else OPERATOR,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


def path(appointment, suffix=""):
    return "/appointments/" + str(appointment.appointment_id) + suffix


def test_consultation_internal_context_requires_its_service_credential(appointment_api):
    client = appointment_api[0]
    appointment = record(appointment_api, status="confirmed")
    target = "/internal/appointments/" + str(appointment.appointment_id)
    assert client.get(target).status_code == 401
    assert client.get(target, headers=service("scheduling-operator")).status_code == 401
    response = client.get(target, headers=service())
    assert response.status_code == 200
    assert response.json()["patient_id"] == str(appointment.patient_id)
    assert response.json()["payment_id"] == str(appointment.payment_id)
    assert (
        client.get("/internal/appointments/" + str(uuid4()), headers=service()).status_code == 404
    )


def test_reads_filtered_for_patient_doctor_admin_platform(appointment_api):
    api = appointment_api
    client, user, tenant, other, ids, *_ = api
    own = record(api)
    assigned_other_patient = record(api, patient=ids["other_patient"])
    other_doctor = record(api, patient=ids["other_patient"], doctor=ids["other_doctor"])
    foreign = record(api, tenant=other, doctor=uuid4())
    expected = {
        "patient": {own.appointment_id, foreign.appointment_id},
        "doctor": {own.appointment_id, assigned_other_patient.appointment_id},
        "admin": {
            own.appointment_id,
            assigned_other_patient.appointment_id,
            other_doctor.appointment_id,
        },
        "platform": {
            own.appointment_id,
            assigned_other_patient.appointment_id,
            other_doctor.appointment_id,
            foreign.appointment_id,
        },
    }
    # Each fixture has unique subjects/tenants; platform may see older test rows.
    for name, visible in expected.items():
        query = {"tenant_id": str(tenant)} if name == "platform" else {}
        result = client.get("/appointments", params=query, headers=user(name))
        assert result.status_code == 200
        returned = {UUID(item["appointment_id"]) for item in result.json()["items"]}
        assert (
            returned == visible - {foreign.appointment_id}
            if name == "platform"
            else returned == visible
        )
        for appointment in (own, assigned_other_patient, other_doctor, foreign):
            response = client.get(path(appointment), headers=user(name))
            assert response.status_code == (200 if appointment.appointment_id in visible else 404)
            if response.status_code == 200:
                assert (
                    "cancellation_reason" not in response.json() and "email" not in response.json()
                )


def test_revocation_immediately_removes_staff_access(appointment_api):
    api = appointment_api
    stored = record(api)
    client, user, _, _, _, _, memberships, *_ = api
    assert client.get(path(stored), headers=user("doctor")).status_code == 200
    memberships["doctor"][0]["status"] = "revoked"
    assert client.get(path(stored), headers=user("doctor")).status_code == 404
    assert client.get("/appointments", headers=user("doctor")).status_code == 403
    assert client.get(path(stored), headers=user("patient")).status_code == 200


def test_staff_collection_rejects_unrelated_selected_tenant(appointment_api):
    api = appointment_api
    record(api)
    for role in ("doctor", "admin"):
        assert (
            api[0]
            .get("/appointments", params={"tenant_id": str(api[3])}, headers=api[1](role))
            .status_code
            == 404
        )
    assert (
        api[0]
        .get("/appointments", params={"tenant_id": str(api[3])}, headers=api[1]("patient"))
        .json()["items"]
        == []
    )


def test_multi_role_read_union_and_cancel_policy(appointment_api):
    api = appointment_api
    assigned = record(api, patient=api[4]["other_patient"])
    own = record(api, patient=api[4]["doctor"], doctor=api[4]["other_doctor"])
    api[5]["roles"]["doctor"] = ["patient"]
    client, user, *_ = api
    assert {
        item["appointment_id"]
        for item in client.get("/appointments", headers=user()).json()["items"]
    } == {str(assigned.appointment_id), str(own.appointment_id)}
    assert (
        client.post(
            path(assigned, "/cancel"), json={"reason": "Request"}, headers=user()
        ).status_code
        == 404
    )
    assert (
        client.post(path(own, "/cancel"), json={"reason": "Request"}, headers=user()).status_code
        == 200
    )


def test_filters_cursor_binding_and_same_timestamp_order(appointment_api):
    api = appointment_api
    start = datetime.now(timezone.utc) + timedelta(days=3)
    # Distinct doctors permit tied starts_at; UUID is the stable second key.
    stored = [record(api, doctor=uuid4(), start=start) for _ in range(3)]
    client, user, tenant, *_ = api
    params = {
        "tenant_id": str(tenant),
        "status": "held",
        "from": start.isoformat(),
        "to": (start + timedelta(hours=1)).isoformat(),
        "limit": 1,
    }
    seen, cursor = [], None
    while True:
        page = client.get(
            "/appointments",
            params=params | ({"cursor": cursor} if cursor else {}),
            headers=user("patient"),
        ).json()
        seen.extend(UUID(item["appointment_id"]) for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(row.appointment_id for row in stored)
    first = client.get("/appointments", params=params, headers=user("patient")).json()[
        "next_cursor"
    ]
    for change in (
        {"status": "cancelled"},
        {"tenant_id": str(api[3])},
        {"from": (start - timedelta(hours=1)).isoformat()},
    ):
        assert (
            client.get(
                "/appointments", params=params | {"cursor": first} | change, headers=user("patient")
            ).status_code
            == 422
        )
    assert (
        client.get(
            "/appointments", params=params | {"cursor": first}, headers=user("admin")
        ).status_code
        == 422
    )
    for bad in ("", first + "x"):
        assert (
            client.get(
                "/appointments", params=params | {"cursor": bad}, headers=user("patient")
            ).status_code
            == 422
        )
    api[5]["roles"]["patient"] = ["patient", "platform_admin"]
    assert (
        client.get(
            "/appointments", params=params | {"cursor": first}, headers=user("patient")
        ).status_code
        == 422
    )


def test_elapsed_holds_read_as_expired_without_worker(appointment_api):
    api = appointment_api
    stored = record(api, expired=True)
    client, user, *_ = api
    assert client.get(path(stored), headers=user("patient")).json()["status"] == "expired"
    assert (
        client.get("/appointments", params={"status": "held"}, headers=user("patient")).json()[
            "items"
        ]
        == []
    )
    assert client.get(
        "/appointments", params={"status": "expired"}, headers=user("patient")
    ).json()["items"][0]["appointment_id"] == str(stored.appointment_id)


@pytest.mark.parametrize("status", ["held", "pending_payment", "confirmed"])
@pytest.mark.parametrize("actor", ["patient", "admin"])
def test_cancel_persists_reason_actor_and_preserves_snapshot(appointment_api, status, actor):
    api = appointment_api
    stored = record(api, status=status)
    client, user, _, _, ids, _, _, engine = api
    cache = client.app.state.hold_cache
    if cache.client is not None:
        cache.client.set(cache.key(stored.slot_id), str(stored.appointment_id), px=60_000)
    response = client.post(
        path(stored, "/cancel"), json={"reason": "  Patient request  "}, headers=user(actor)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "cancelled" and data["payment_id"] == (
        str(stored.payment_id) if stored.payment_id else None
    )
    assert data["consultation_price"]["amount_minor"] == 3210
    assert data["hold_expires_at"] == (
        stored.hold_expires_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if stored.hold_expires_at
        else None
    )
    if status == "confirmed":
        assert data["payment_resolution"] == "refund_required"
    with Session(engine) as session:
        saved = session.get(Appointment, stored.appointment_id)
        assert saved.cancellation_reason == "Patient request"
        assert saved.cancelled_by_subject_id == ids[actor] and saved.cancelled_at is not None
        updated_at = saved.updated_at
    repeated = client.post(
        path(stored, "/cancel"), json={"reason": "Different retry"}, headers=user(actor)
    )
    assert repeated.status_code == 200
    with Session(engine) as session:
        saved = session.get(Appointment, stored.appointment_id)
        assert saved.updated_at == updated_at and saved.cancellation_reason == "Patient request"
    if cache.client is not None:
        assert cache.client.get(cache.key(stored.slot_id)) is None


@pytest.mark.parametrize("actor", ["other_patient", "doctor", "platform"])
def test_cancel_denied_even_when_metadata_visible(appointment_api, actor):
    api = appointment_api
    stored = record(api, status="completed")
    response = api[0].post(
        path(stored, "/cancel"), json={"reason": "Request"}, headers=api[1](actor)
    )
    assert response.status_code == 404


@pytest.mark.parametrize("status", ["expired", "in_progress", "completed", "no_show"])
def test_terminal_or_started_appointments_cannot_cancel(appointment_api, status):
    api = appointment_api
    stored = record(api, status=status)
    response = api[0].post(
        path(stored, "/cancel"), json={"reason": "Request"}, headers=api[1]("patient")
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "invalid_appointment_transition"
    )


def test_cancellation_at_expiry_persists_expired_state(appointment_api, monkeypatch):
    api = appointment_api
    stored = record(api)
    monkeypatch.setattr(appointments, "server_now", lambda _: stored.hold_expires_at)
    response = api[0].post(
        path(stored, "/cancel"), json={"reason": "Request"}, headers=api[1]("patient")
    )
    assert response.status_code == 409
    with Session(api[-1]) as session:
        assert session.get(Appointment, stored.appointment_id).status == "expired"


def test_confirmed_cancel_at_start_is_rejected(appointment_api, monkeypatch):
    api = appointment_api
    stored = record(api, status="confirmed")
    monkeypatch.setattr(appointments, "server_now", lambda _: stored.starts_at)
    response = api[0].post(
        path(stored, "/cancel"), json={"reason": "Request"}, headers=api[1]("patient")
    )
    assert response.status_code == 409


@pytest.mark.parametrize("reason", ["", "   ", "<script>", "x" * 2001])
def test_cancel_reason_validation(appointment_api, reason):
    api = appointment_api
    stored = record(api)
    assert (
        api[0]
        .post(path(stored, "/cancel"), json={"reason": reason}, headers=api[1]("patient"))
        .status_code
        == 422
    )


def test_service_start_complete_and_operator_no_show(appointment_api):
    api = appointment_api
    now = datetime.now(timezone.utc)
    active = record(api, status="confirmed", start=now - timedelta(minutes=5))
    client = api[0]
    route = "/internal" + path(active)
    assert client.post(route + "/start", headers=service()).json()["status"] == "in_progress"
    assert client.post(route + "/complete", headers=service()).json()["status"] == "completed"
    assert client.post(route + "/start", headers=service()).status_code == 409
    assert client.post(route + "/complete", headers=service()).status_code == 409
    past = record(api, status="confirmed", start=now - timedelta(hours=1))
    assert (
        client.post(
            "/internal" + path(past, "/no-show"), headers=service("scheduling-operator")
        ).json()["status"]
        == "no_show"
    )
    assert client.post("/internal" + path(past, "/complete"), headers=service()).status_code == 409


@pytest.mark.parametrize(
    "action,caller",
    [("start", "consultation"), ("complete", "consultation"), ("no-show", "scheduling-operator")],
)
def test_internal_actions_reject_cognito_and_wrong_services(appointment_api, action, caller):
    api = appointment_api
    stored = record(api, status="confirmed")
    route = "/internal" + path(stored, "/" + action)
    for headers in (
        {},
        api[1]("patient"),
        api[1]("platform"),
        service("scheduling-operator" if caller == "consultation" else "consultation"),
    ):
        assert api[0].post(route, headers=headers).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"sub": "billing"},
        {"aud": "other"},
        {"iss": "other"},
        {"exp": int(time.time()) + 1000},
        {"iat": int(time.time()) + 100},
    ],
)
def test_service_token_validation(appointment_api, changes):
    stored = record(appointment_api, status="confirmed")
    assert (
        appointment_api[0]
        .post("/internal" + path(stored, "/start"), headers=service(**changes))
        .status_code
        == 401
    )


def test_internal_windows_at_exact_boundaries(appointment_api, monkeypatch):
    api = appointment_api
    stored = record(api, status="confirmed")
    client, route = api[0], "/internal" + path(stored)
    for now in (stored.starts_at - timedelta(microseconds=1), stored.ends_at):
        monkeypatch.setattr(appointments, "server_now", lambda _, now=now: now)
        assert client.post(route + "/start", headers=service()).status_code == 409
    monkeypatch.setattr(
        appointments, "server_now", lambda _: stored.ends_at - timedelta(microseconds=1)
    )
    assert (
        client.post(route + "/no-show", headers=service("scheduling-operator")).status_code == 409
    )
    monkeypatch.setattr(appointments, "server_now", lambda _: stored.ends_at)
    assert (
        client.post(route + "/no-show", headers=service("scheduling-operator")).status_code == 200
    )
    other = record(api, status="confirmed", start=stored.ends_at + timedelta(hours=1))
    monkeypatch.setattr(appointments, "server_now", lambda _: other.starts_at)
    assert client.post("/internal" + path(other, "/start"), headers=service()).status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"from": "2026-10-14T00:00:00"},
        {"from": "123"},
        {"from": "2030-01-02T00:00:00Z", "to": "2030-01-01T00:00:00Z"},
        {"status": "paid"},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_appointment_filter_validation(appointment_api, change):
    assert (
        appointment_api[0]
        .get("/appointments", params=change, headers=appointment_api[1]("patient"))
        .status_code
        == 422
    )


def test_missing_service_secret_fails_closed():
    app = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(app) as client:
        assert (
            client.post(
                "/internal/appointments/" + str(uuid4()) + "/start", headers=service()
            ).status_code
            == 503
        )


def test_concurrent_cancel_does_not_change_first_reason(appointment_api):
    api = appointment_api
    stored = record(api)
    barrier = Barrier(2)

    def cancel(index):
        barrier.wait(timeout=10)
        return api[0].post(
            path(stored, "/cancel"), json={"reason": f"Request {index}"}, headers=api[1]("patient")
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(cancel, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    with Session(api[-1]) as session:
        saved = session.get(Appointment, stored.appointment_id)
        assert saved.cancellation_reason in {"Request 0", "Request 1"}
        assert saved.cancelled_by_subject_id == api[4]["patient"]


def test_delayed_cancel_cleanup_cannot_delete_replacement_hold(appointment_api, monkeypatch):
    api = appointment_api
    stored = record(api)
    cache = api[0].app.state.hold_cache
    if cache.client is None:
        pytest.skip("Set TEST_REDIS_URL")
    published, proceed = Event(), Event()
    actual_release = cache.release

    def delayed_release(slot_id, appointment_id):
        if appointment_id == stored.appointment_id:
            published.set()
            assert proceed.wait(timeout=10)
        return actual_release(slot_id, appointment_id)

    monkeypatch.setattr(cache, "release", delayed_release)
    with ThreadPoolExecutor(max_workers=1) as executor:
        cancellation = executor.submit(
            api[0].post,
            path(stored, "/cancel"),
            json={"reason": "Request"},
            headers=api[1]("patient"),
        )
        try:
            assert published.wait(timeout=10)
            replacement = api[0].post(
                "/appointments",
                json={"tenant_id": str(stored.tenant_id), "slot_id": str(stored.slot_id)},
                headers=api[1]("other_patient"),
            )
            assert replacement.status_code == 201
        finally:
            proceed.set()
        assert cancellation.result().status_code == 200
    assert cache.client.get(cache.key(stored.slot_id)) == replacement.json()["appointment_id"]
    cache.client.delete(cache.key(stored.slot_id))


def test_start_cancel_race_cannot_leave_invalid_combination(appointment_api, monkeypatch):
    api = appointment_api
    stored = record(api, status="confirmed")
    # Both actions see exactly start time: cancellation is too late; start is legal.
    monkeypatch.setattr(appointments, "server_now", lambda _: stored.starts_at)
    barrier = Barrier(2)

    def cancel():
        barrier.wait(timeout=10)
        return api[0].post(
            path(stored, "/cancel"), json={"reason": "Request"}, headers=api[1]("patient")
        )

    def start():
        barrier.wait(timeout=10)
        return api[0].post("/internal" + path(stored, "/start"), headers=service())

    with ThreadPoolExecutor(max_workers=2) as executor:
        cancellation, initiation = executor.submit(cancel), executor.submit(start)
        assert cancellation.result().status_code == 409 and initiation.result().status_code == 200
    with Session(api[-1]) as session:
        saved = session.get(Appointment, stored.appointment_id)
        assert saved.status == "in_progress" and saved.cancellation_reason is None


def test_cancel_does_not_release_newer_holder(appointment_api):
    api = appointment_api
    old = record(api, status="cancelled")
    client, user, *_ = api
    if client.app.state.hold_cache.client is None:
        pytest.skip("Set TEST_REDIS_URL")
    replacement = client.post(
        "/appointments",
        json={"tenant_id": str(old.tenant_id), "slot_id": str(old.slot_id)},
        headers=user("other_patient"),
    )
    assert replacement.status_code == 201
    assert (
        client.post(
            path(old, "/cancel"), json={"reason": "Retry"}, headers=user("patient")
        ).status_code
        == 200
    )
    cache = client.app.state.hold_cache
    assert cache.client.get(cache.key(old.slot_id)) == replacement.json()["appointment_id"]
    cache.client.delete(cache.key(old.slot_id))
