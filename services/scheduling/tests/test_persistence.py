import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import Appointment, AvailabilitySlot


def test_database_url_validation(monkeypatch):
    monkeypatch.delenv("SERVICE_DATABASE_URL", raising=False)
    for url in (None, "sqlite:///scheduling.db", "postgresql+psycopg://host", "not a url"):
        with pytest.raises(ValueError):
            create_database_engine(url)


@pytest.fixture(scope="module")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    if os.environ.get("SCHEDULING_TEST_ALLOW_RESET") != "1":
        pytest.fail("Set SCHEDULING_TEST_ALLOW_RESET=1: tests delete scheduling data")
    old_url = os.environ.get("SERVICE_DATABASE_URL")
    os.environ["SERVICE_DATABASE_URL"] = url
    engine = create_database_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        public_tables = inspect(engine).get_table_names(schema="public")
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        # Prior API tests may have replaced withdrawn slots. Clear disposable
        # test rows before verifying rollback to S01's stricter overlap rule.
        with engine.begin() as connection:
            connection.execute(
                text("TRUNCATE scheduling.appointments, scheduling.availability_slots")
            )
        slot = create_slot(engine)
        appointment = create_appointment(engine, slot)
        command.downgrade(config, "0001")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT appointment_id FROM scheduling.appointments "
                        "WHERE appointment_id=:id"
                    ),
                    {"id": appointment.appointment_id},
                )
                == appointment.appointment_id
            )
        command.upgrade(config, "head")
        command.check(config)
        assert sorted(inspect(engine).get_table_names(schema="scheduling")) == [
            "alembic_version",
            "appointments",
            "availability_slots",
        ]
        yield engine
        command.downgrade(config, "base")
        assert inspect(engine).get_table_names(schema="scheduling") == ["alembic_version"]
        assert inspect(engine).get_table_names(schema="public") == public_tables
        with engine.connect() as connection:
            for function in ("protect_slot", "protect_appointment"):
                assert (
                    connection.scalar(text(f"SELECT to_regprocedure('scheduling.{function}()')"))
                    is None
                )
            assert connection.scalar(text("SELECT count(*) FROM public.s01_sentinel")) == 1
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        if old_url is None:
            os.environ.pop("SERVICE_DATABASE_URL", None)
        else:
            os.environ["SERVICE_DATABASE_URL"] = old_url


def create_slot(engine, **fields):
    values = {
        "tenant_id": uuid4(),
        "doctor_id": uuid4(),
        "starts_at": datetime.now(timezone.utc) + timedelta(days=1),
    } | fields
    values.setdefault("ends_at", values["starts_at"] + timedelta(minutes=30))
    with Session(engine, expire_on_commit=False) as session, session.begin():
        slot = AvailabilitySlot(**values)
        session.add(slot)
        session.flush()
        return slot


def create_appointment(engine, slot=None, **fields):
    slot = slot or create_slot(engine)
    values = {
        "tenant_id": slot.tenant_id,
        "doctor_id": slot.doctor_id,
        "slot_id": slot.slot_id,
        "starts_at": slot.starts_at,
        "ends_at": slot.ends_at,
        "patient_id": uuid4(),
        "hold_expires_at": datetime.now(timezone.utc) + timedelta(minutes=9),
        "consultation_price_minor": 2500,
    } | fields
    with Session(engine, expire_on_commit=False) as session, session.begin():
        appointment = Appointment(**values)
        session.add(appointment)
        session.flush()
        return appointment


def test_defaults_utc_and_sql_timestamp_trigger(database):
    appointment = create_appointment(database)
    assert isinstance(appointment.appointment_id, UUID)
    assert (appointment.status, appointment.currency, appointment.payment_resolution) == (
        "held",
        "SGD",
        "none",
    )
    assert appointment.payment_id is None
    assert appointment.created_at.utcoffset() == timedelta(0)
    with database.begin() as connection:
        updated = connection.execute(
            text("""
            UPDATE scheduling.appointments SET status='pending_payment',
                payment_id=:payment, payment_resolution='awaiting_payment',
                created_at='2000-01-01', updated_at='2000-01-01'
            WHERE appointment_id=:id RETURNING created_at, updated_at
        """),
            {"id": appointment.appointment_id, "payment": uuid4()},
        ).one()
        assert updated.created_at == appointment.created_at
        assert updated.updated_at > appointment.updated_at


@pytest.mark.parametrize("minutes", [0, -30, 15, 60])
def test_fixed_slot_duration(database, minutes):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(IntegrityError):
        create_slot(database, starts_at=start, ends_at=start + timedelta(minutes=minutes))


@pytest.mark.parametrize("offset", [-15, 0, 15])
def test_doctor_overlap_across_clinics(database, offset):
    slot = create_slot(database)
    with pytest.raises(IntegrityError) as error:
        create_slot(
            database, doctor_id=slot.doctor_id, starts_at=slot.starts_at + timedelta(minutes=offset)
        )
    assert error.value.orig.diag.constraint_name == "ex_slots_doctor_overlap"


def test_half_open_intervals_and_other_doctors(database):
    slot = create_slot(database)
    create_slot(database, doctor_id=slot.doctor_id, starts_at=slot.ends_at)
    create_slot(database, tenant_id=slot.tenant_id, starts_at=slot.starts_at)


@pytest.mark.parametrize("field", ["tenant_id", "doctor_id", "slot_id", "starts_at", "ends_at"])
def test_appointment_must_match_slot_context(database, field):
    slot = create_slot(database)
    value = uuid4() if field.endswith("_id") else getattr(slot, field) + timedelta(minutes=1)
    with pytest.raises(IntegrityError) as error:
        create_appointment(database, slot, **{field: value})
    assert error.value.orig.diag.constraint_name == "fk_appointments_slot_context"


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "booked"},
        {"payment_resolution": "paid"},
        {"consultation_price_minor": -1},
        {"consultation_price_minor": 9007199254740992},
        {"currency": "USD"},
        {"hold_expires_at": None},
        {"status": "pending_payment", "hold_expires_at": None},
        {"status": "expired", "hold_expires_at": None},
        {"status": "confirmed"},
        {"hold_expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        {"hold_expires_at": datetime.now(timezone.utc) + timedelta(hours=1)},
    ],
)
def test_invalid_appointment_values(database, fields):
    with pytest.raises(IntegrityError):
        create_appointment(database, **fields)


@pytest.mark.parametrize(
    "field",
    [
        "tenant_id",
        "patient_id",
        "doctor_id",
        "slot_id",
        "appointment_id",
        "starts_at",
        "ends_at",
        "consultation_price_minor",
        "currency",
        "hold_expires_at",
    ],
)
def test_immutable_appointment_context_and_price(database, field):
    appointment = create_appointment(database)
    value = (
        uuid4()
        if field.endswith("_id")
        else {
            "starts_at": appointment.starts_at + timedelta(minutes=1),
            "ends_at": appointment.ends_at + timedelta(minutes=1),
            "hold_expires_at": appointment.hold_expires_at + timedelta(seconds=1),
            "consultation_price_minor": 3000,
            "currency": "USD",
        }.get(field)
    )
    with pytest.raises(IntegrityError):
        with database.begin() as connection:
            connection.execute(
                text(f"UPDATE scheduling.appointments SET {field}=:value WHERE appointment_id=:id"),
                {"value": value, "id": appointment.appointment_id},
            )


def test_slot_context_immutable_and_history_retained(database):
    slot = create_slot(database)
    with pytest.raises(IntegrityError):
        with database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE scheduling.availability_slots SET doctor_id=:doctor WHERE slot_id=:id"
                ),
                {"doctor": uuid4(), "id": slot.slot_id},
            )
    create_appointment(database, slot, status="cancelled")
    create_appointment(database, slot, status="expired")
    with pytest.raises(IntegrityError):
        with database.begin() as connection:
            connection.execute(
                text("DELETE FROM scheduling.availability_slots WHERE slot_id=:id"),
                {"id": slot.slot_id},
            )


def test_confirmation_clears_hold_and_preserves_price(database):
    appointment = create_appointment(database)
    with Session(database) as session, session.begin():
        stored = session.get(Appointment, appointment.appointment_id)
        stored.status = "confirmed"
        stored.hold_expires_at = None
        stored.payment_id = uuid4()
        stored.payment_resolution = "confirmed"
        session.flush()
        assert stored.consultation_price_minor == 2500
        assert stored.updated_at > appointment.updated_at


@pytest.mark.parametrize("price", [0, 9007199254740991])
def test_money_boundaries_and_hold_at_slot_start(database, price):
    now = datetime.now(timezone.utc)
    slot = create_slot(database, starts_at=now + timedelta(minutes=5))
    appointment = create_appointment(
        database,
        slot,
        consultation_price_minor=price,
        created_at=now,
        hold_expires_at=slot.starts_at,
    )
    assert appointment.consultation_price_minor == price
    assert appointment.hold_expires_at == slot.starts_at


@pytest.mark.parametrize("seconds", [0, 601])
def test_hold_creation_bounds(database, seconds):
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        create_appointment(
            database, created_at=now, hold_expires_at=now + timedelta(seconds=seconds)
        )


def test_hold_cannot_extend_beyond_slot_start(database):
    now = datetime.now(timezone.utc)
    slot = create_slot(database, starts_at=now + timedelta(minutes=5))
    with pytest.raises(IntegrityError):
        create_appointment(
            database, slot, created_at=now, hold_expires_at=slot.starts_at + timedelta(seconds=1)
        )


def test_infinite_slots_rejected(database):
    with pytest.raises(IntegrityError):
        with database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO scheduling.availability_slots
                    (slot_id, tenant_id, doctor_id, starts_at, ends_at)
                VALUES (:slot, :tenant, :doctor, 'infinity', 'infinity')
            """),
                {"slot": uuid4(), "tenant": uuid4(), "doctor": uuid4()},
            )


def test_service_role_isolation(database):
    with database.connect() as connection:
        assert connection.scalar(text("SHOW search_path")) == "public"
        assert connection.scalar(text("SHOW timezone")) == "UTC"
    with pytest.raises(DBAPIError):
        with database.begin() as connection:
            connection.execute(text("CREATE TABLE public.s01_forbidden(id integer)"))
    with pytest.raises(DBAPIError):
        with database.begin() as connection:
            connection.execute(text("UPDATE public.s01_sentinel SET id=2"))
