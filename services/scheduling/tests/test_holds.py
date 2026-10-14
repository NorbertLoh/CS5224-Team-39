import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import redis
import test_api
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_api import list_params, slot_body

from app import booking
from app.expire_holds import expire_batch
from app.holds import HoldCache, expire_slot_holds
from app.models import ACTIVE_RESERVATION_STATES, Appointment, AvailabilitySlot
from app.settings import Settings

# Reuse the real PostgreSQL and signed upstream HTTP fixtures from S02.
api = test_api.api
api_database = test_api.api_database


@pytest.fixture
def holds(api):
    if not os.environ.get("TEST_REDIS_URL"):
        pytest.skip("Set TEST_REDIS_URL to disposable Redis for hold checks")
    assert api[0].app.state.hold_cache.ready()
    yield api
    cache = api[0].app.state.hold_cache
    # Never FLUSHDB: remove only this fixture's slot keys.
    with Session(api[-1]) as session:
        slots = session.scalars(
            select(AvailabilitySlot.slot_id).where(AvailabilitySlot.tenant_id.in_((api[2], api[3])))
        ).all()
    for slot_id in slots:
        cache.client.delete(cache.key(slot_id))


def make_slot(api, start=None):
    client, user, tenant, *_ = api
    body = slot_body(start)
    response = client.post(f"/clinics/{tenant}/slots", json=body, headers=user())
    assert response.status_code == 201, response.text
    return response.json(), body


def hold_body(api, slot):
    return {"tenant_id": str(api[2]), "slot_id": slot["slot_id"]}


def persisted_hold(api, slot, *, status="held", seconds=-1):
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=seconds)
    with Session(api[-1], expire_on_commit=False) as session, session.begin():
        stored = session.get(AvailabilitySlot, UUID(slot["slot_id"]))
        appointment = Appointment(
            patient_id=api[4]["patient"],
            tenant_id=stored.tenant_id,
            slot_id=stored.slot_id,
            doctor_id=stored.doctor_id,
            starts_at=stored.starts_at,
            ends_at=stored.ends_at,
            status=status,
            hold_expires_at=expiry,
            consultation_price_minor=2500,
            created_at=now - timedelta(minutes=5),
            updated_at=now,
        )
        session.add(appointment)
        session.flush()
        return appointment


def test_hold_context_price_deadline_and_real_redis_ttl(holds):
    client, user, tenant, _, ids, state, _, engine = holds
    slot, body = make_slot(holds)
    state["price"] = 3210
    response = client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["patient_id"] == str(ids["patient"])
    assert result["doctor_id"] == str(ids["doctor"])
    assert result["status"] == "held" and result["payment_id"] is None
    assert result["consultation_price"] == {"amount_minor": 3210, "currency": "SGD"}
    cache = client.app.state.hold_cache
    assert cache.client.get(cache.key(slot["slot_id"])) == result["appointment_id"]
    assert 590_000 < cache.client.pttl(cache.key(slot["slot_id"])) <= 600_000
    with Session(engine) as session:
        stored = session.get(Appointment, UUID(result["appointment_id"]))
        assert stored.hold_expires_at - stored.created_at == timedelta(minutes=10)
    assert (
        client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()["items"][0][
            "availability"
        ]
        == "unavailable"
    )
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 409


def test_deadline_capped_at_slot_start(holds):
    slot, _ = make_slot(holds, datetime.now(timezone.utc) + timedelta(minutes=2))
    client, user, *_ = holds
    response = client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))
    assert response.status_code == 201
    assert response.json()["hold_expires_at"] == response.json()["starts_at"]


def test_many_patients_one_reservation_and_no_deadline_extension(holds):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    barrier = Barrier(4)

    def reserve(index):
        headers = user("patient" if index % 2 else "other_patient")
        barrier.wait(timeout=10)
        return client.post("/appointments", json=hold_body(holds, slot), headers=headers)

    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(reserve, range(4)))
    assert sorted(response.status_code for response in responses) == [201, 409, 409, 409]
    winner = next(response.json() for response in responses if response.status_code == 201)
    with Session(holds[-1]) as session:
        stored = session.scalars(
            select(Appointment).where(
                Appointment.slot_id == UUID(slot["slot_id"]),
                Appointment.status.in_(ACTIVE_RESERVATION_STATES),
            )
        ).all()
        assert len(stored) == 1 and str(stored[0].appointment_id) == winner["appointment_id"]
        deadline = stored[0].hold_expires_at
    assert (
        client.post(
            "/appointments", json=hold_body(holds, slot), headers=user("patient")
        ).status_code
        == 409
    )
    with Session(holds[-1]) as session:
        assert session.get(Appointment, UUID(winner["appointment_id"])).hold_expires_at == deadline


@pytest.mark.parametrize("status", ["held", "pending_payment"])
def test_expired_hold_reallocated_atomically(holds, status):
    slot, body = make_slot(holds)
    old = persisted_hold(holds, slot, status=status)
    client, user, tenant, *_ = holds
    cache = client.app.state.hold_cache
    cache.client.set(cache.key(slot["slot_id"]), str(old.appointment_id), px=60_000)
    assert (
        client.get(f"/clinics/{tenant}/slots", params=list_params(body)).json()["items"][0][
            "availability"
        ]
        == "available"
    )
    response = client.post(
        "/appointments", json=hold_body(holds, slot), headers=user("other_patient")
    )
    assert response.status_code == 201, response.text
    with Session(holds[-1]) as session:
        stored = session.get(Appointment, old.appointment_id)
        assert stored.status == "expired" and stored.hold_expires_at == old.hold_expires_at
    assert cache.client.get(cache.key(slot["slot_id"])) == response.json()["appointment_id"]
    cache.release(slot["slot_id"], old.appointment_id)
    assert cache.client.get(cache.key(slot["slot_id"])) == response.json()["appointment_id"]


def test_exact_expiry_boundary_and_sweep_skips_locked_slot(holds):
    slot, _ = make_slot(holds)
    old = persisted_hold(holds, slot, seconds=30)
    cache, engine = holds[0].app.state.hold_cache, holds[-1]
    with Session(engine) as session, session.begin():
        session.scalar(
            select(AvailabilitySlot)
            .where(AvailabilitySlot.slot_id == old.slot_id)
            .with_for_update()
        )
        assert (
            expire_slot_holds(
                session, old.slot_id, old.hold_expires_at - timedelta(microseconds=1), cache
            )
            == 0
        )
        assert expire_slot_holds(session, old.slot_id, old.hold_expires_at, cache) == 1
    slot2, _ = make_slot(holds, datetime.now(timezone.utc) + timedelta(days=2))
    old2 = persisted_hold(holds, slot2)
    with Session(engine) as locked, locked.begin():
        locked.scalar(
            select(AvailabilitySlot)
            .where(AvailabilitySlot.slot_id == old2.slot_id)
            .with_for_update()
        )
        assert expire_batch(engine, cache) == 0
    assert expire_batch(engine, cache) == 1
    assert expire_batch(engine, cache) == 0


def test_worker_and_booking_compete_without_deleting_new_cache(holds):
    slot, _ = make_slot(holds)
    old = persisted_hold(holds, slot)
    client, user, *_ = holds
    cache = client.app.state.hold_cache
    barrier = Barrier(2)

    def sweep():
        barrier.wait(timeout=10)
        return expire_batch(holds[-1], cache)

    def reserve():
        barrier.wait(timeout=10)
        return client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker, request = executor.submit(sweep), executor.submit(reserve)
        worker.result()
        response = request.result()
    assert response.status_code == 201
    cache.release(slot["slot_id"], old.appointment_id)
    assert cache.client.get(cache.key(slot["slot_id"])) == response.json()["appointment_id"]


def test_withdrawal_and_booking_race(holds):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    barrier = Barrier(2)

    def withdraw():
        barrier.wait(timeout=10)
        return client.delete("/slots/" + slot["slot_id"], headers=user())

    def reserve():
        barrier.wait(timeout=10)
        return client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        deletion, creation = executor.submit(withdraw), executor.submit(reserve)
        statuses = (deletion.result().status_code, creation.result().status_code)
    assert statuses in {(204, 404), (409, 201)}, statuses
    with Session(holds[-1]) as session:
        stored = session.get(AvailabilitySlot, UUID(slot["slot_id"]))
        active = session.scalar(
            select(Appointment).where(
                Appointment.slot_id == stored.slot_id,
                Appointment.status.in_(ACTIVE_RESERVATION_STATES),
            )
        )
        assert not (stored.withdrawn_at is not None and active is not None)


def test_expired_hold_does_not_block_withdrawal(holds):
    slot, _ = make_slot(holds)
    old = persisted_hold(holds, slot)
    assert holds[0].delete("/slots/" + slot["slot_id"], headers=holds[1]()).status_code == 204
    with Session(holds[-1]) as session:
        assert session.get(Appointment, old.appointment_id).status == "expired"


def test_many_patients_race_to_reallocate_expired_hold(holds):
    slot, _ = make_slot(holds)
    old = persisted_hold(holds, slot)
    client, user, *_ = holds
    barrier = Barrier(4)

    def reserve(index):
        headers = user("patient" if index % 2 else "other_patient")
        barrier.wait(timeout=10)
        return client.post("/appointments", json=hold_body(holds, slot), headers=headers)

    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(reserve, range(4)))
    assert sorted(response.status_code for response in responses) == [201, 409, 409, 409]
    with Session(holds[-1]) as session:
        assert session.get(Appointment, old.appointment_id).status == "expired"
        assert (
            len(
                session.scalars(
                    select(Appointment).where(
                        Appointment.slot_id == old.slot_id,
                        Appointment.status.in_(ACTIVE_RESERVATION_STATES),
                    )
                ).all()
            )
            == 1
        )


def test_missing_redis_key_does_not_release_capacity(holds):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    body = hold_body(holds, slot)
    assert client.post("/appointments", json=body, headers=user("patient")).status_code == 201
    cache = client.app.state.hold_cache
    cache.client.delete(cache.key(slot["slot_id"]))
    assert client.post("/appointments", json=body, headers=user("other_patient")).status_code == 409


def test_redis_outage_cannot_allow_double_booking(holds, monkeypatch):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    cache = client.app.state.hold_cache

    def unavailable(*args, **kwargs):
        raise redis.ConnectionError("Synthetic outage")

    monkeypatch.setattr(cache.client, "set", unavailable)
    monkeypatch.setattr(cache.client, "eval", unavailable)
    assert (
        client.post(
            "/appointments", json=hold_body(holds, slot), headers=user("patient")
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/appointments", json=hold_body(holds, slot), headers=user("other_patient")
        ).status_code
        == 409
    )


def test_failed_commit_releases_own_cache_key(holds, monkeypatch):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    with monkeypatch.context() as patch:
        patch.setattr(
            Session,
            "commit",
            lambda self: (_ for _ in ()).throw(RuntimeError("Synthetic commit failure")),
        )
        with pytest.raises(RuntimeError):
            client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))
    cache = client.app.state.hold_cache
    assert cache.client.get(cache.key(slot["slot_id"])) is None
    with Session(holds[-1]) as session:
        assert (
            session.scalar(select(Appointment).where(Appointment.slot_id == UUID(slot["slot_id"])))
            is None
        )
    assert (
        client.post(
            "/appointments", json=hold_body(holds, slot), headers=user("patient")
        ).status_code
        == 201
    )


def test_hold_expiring_during_cache_write_not_reported_held(holds, monkeypatch):
    slot, _ = make_slot(holds)
    client, user, *_ = holds
    cache = client.app.state.hold_cache
    times = []
    actual_now = booking.server_now

    def clock(session):
        now = actual_now(session)
        times.append(now)
        return now if len(times) == 1 else times[0] + timedelta(minutes=10)

    monkeypatch.setattr(booking, "server_now", clock)
    response = client.post("/appointments", json=hold_body(holds, slot), headers=user("patient"))
    assert response.status_code == 409 and response.json()["error"]["code"] == "hold_expired"
    assert cache.client.get(cache.key(slot["slot_id"])) is None
    with Session(holds[-1]) as session:
        assert (
            session.scalar(
                select(Appointment).where(Appointment.slot_id == UUID(slot["slot_id"]))
            ).status
            == "expired"
        )


@pytest.mark.parametrize("name", ["doctor", "admin", "platform"])
def test_non_patient_roles_cannot_hold(holds, name):
    slot, _ = make_slot(holds)
    assert (
        holds[0]
        .post("/appointments", json=hold_body(holds, slot), headers=holds[1](name))
        .status_code
        == 403
    )


def test_staff_with_patient_role_can_hold_using_own_subject(holds):
    slot, _ = make_slot(holds)
    holds[5]["roles"]["other_doctor"] = ["patient"]
    response = holds[0].post(
        "/appointments", json=hold_body(holds, slot), headers=holds[1]("other_doctor")
    )
    assert response.status_code == 201
    assert response.json()["patient_id"] == str(holds[4]["other_doctor"])


@pytest.mark.parametrize("field", ["patient_id", "doctor_id", "price", "hold_expires_at", "status"])
def test_browser_cannot_supply_trusted_hold_fields(holds, field):
    slot, _ = make_slot(holds)
    assert (
        holds[0]
        .post(
            "/appointments",
            json=hold_body(holds, slot) | {field: "forged"},
            headers=holds[1]("patient"),
        )
        .status_code
        == 422
    )


def test_hold_gate_rechecks_tenant_doctor_and_slot(holds):
    slot, _ = make_slot(holds)
    client, user, _, other_tenant, _, state, *_ = holds
    body, headers = hold_body(holds, slot), user("patient")
    assert (
        client.post(
            "/appointments", json=body | {"tenant_id": str(other_tenant)}, headers=headers
        ).status_code
        == 404
    )
    state["directory"] = []
    assert client.post("/appointments", json=body, headers=headers).status_code == 409
    state["active"] = False
    assert client.post("/appointments", json=body, headers=headers).status_code == 409
    state["active"] = True
    state["directory"] = [holds[4]["doctor"]]
    assert client.delete("/slots/" + slot["slot_id"], headers=user()).status_code == 204
    assert client.post("/appointments", json=body, headers=headers).status_code == 404


def test_past_slot_cannot_be_held(holds):
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    with Session(holds[-1], expire_on_commit=False) as session, session.begin():
        slot = AvailabilitySlot(
            tenant_id=holds[2],
            doctor_id=holds[4]["doctor"],
            starts_at=now,
            ends_at=now + timedelta(minutes=30),
        )
        session.add(slot)
        session.flush()
        body = {"tenant_id": str(slot.tenant_id), "slot_id": str(slot.slot_id)}
    assert holds[0].post("/appointments", json=body, headers=holds[1]("patient")).status_code == 409


@pytest.mark.parametrize("state", ["held", "pending_payment", "confirmed", "in_progress"])
def test_database_constraint_protects_direct_writes(holds, state):
    slot, _ = make_slot(holds)
    old = persisted_hold(holds, slot, seconds=60)
    with Session(holds[-1]) as session, session.begin():
        stored = session.get(Appointment, old.appointment_id)
        stored.status = state
        if state in {"confirmed", "in_progress"}:
            stored.hold_expires_at = None
    with pytest.raises(IntegrityError) as error:
        persisted_hold(holds, slot, seconds=60)
    assert error.value.orig.diag.constraint_name == "uq_appointments_active_slot"


def test_real_redis_absolute_expiry():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL")
    cache = HoldCache(Settings(_env_file=None, environment="test", redis_url=url))
    slot_id, appointment_id = uuid4(), uuid4()
    from types import SimpleNamespace

    try:
        cache.mirror(
            SimpleNamespace(
                slot_id=slot_id,
                appointment_id=appointment_id,
                hold_expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=150),
            )
        )
        assert cache.client.get(cache.key(slot_id)) == str(appointment_id)
        time.sleep(0.25)
        assert cache.client.get(cache.key(slot_id)) is None
    finally:
        cache.client.delete(cache.key(slot_id))
        cache.close()


@pytest.mark.parametrize(
    "url", ["http://localhost", "redis://localhost/?password=secret", "redis://localhost/not-a-db"]
)
def test_redis_configuration_guards(url):
    with pytest.raises(ValueError):
        Settings(_env_file=None, redis_url=url)
