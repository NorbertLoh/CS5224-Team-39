from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import CatalogueItem, Order, OrderItem


def new_order(**changes):
    return Order(
        **dict(
            tenant_id=uuid4(),
            patient_id=uuid4(),
            appointment_id=uuid4(),
            prescription_id=uuid4(),
            medication_subtotal_minor=100,
        )
        | changes
    )


def test_migration_roundtrip_and_schema_isolation(sessions, database):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    public_before = inspect(database).get_table_names(schema="public")
    assert sorted(inspect(database).get_table_names(schema="fulfilment")) == [
        "alembic_version",
        "catalogue_items",
        "event_inbox",
        "order_items",
        "order_requests",
        "orders",
        "quote_requests",
        "quotes",
    ]
    with sessions() as db:
        with pytest.raises(DBAPIError):
            db.execute(text("SELECT * FROM public.d01_sentinel"))
    command.downgrade(config, "base")
    assert inspect(database).get_table_names(schema="fulfilment") == ["alembic_version"]
    assert inspect(database).get_table_names(schema="public") == public_before
    command.upgrade(config, "head")
    command.check(config)


def test_prescription_uniqueness(sessions):
    rx = uuid4()
    with sessions.begin() as db:
        db.add(new_order(prescription_id=rx))
    with pytest.raises(IntegrityError), sessions.begin() as db:
        db.add(new_order(prescription_id=rx, status="cancelled"))


@pytest.mark.parametrize(
    "values",
    [
        {"medication_subtotal_minor": -1},
        {"medication_subtotal_minor": 9007199254740992},
        {"status": "invalid"},
        {"medicine_status": "invalid"},
        {"payment_status": "invalid"},
        {"delivery_fee_minor": 20},
        {"total_minor": 120},
        {"delivery_fee_minor": 20, "total_minor": 121},
    ],
)
def test_order_constraints(sessions, values):
    with pytest.raises(IntegrityError), sessions.begin() as db:
        db.add(new_order(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"unit_price_minor": -1},
        {"line_total_minor": 101},
        {"position": -1},
    ],
)
def test_item_constraints(sessions, values):
    with pytest.raises(IntegrityError), sessions.begin() as db:
        order = new_order()
        order.items = [
            OrderItem(
                **dict(
                    prescription_item_id=uuid4(),
                    medication_id=uuid4(),
                    position=0,
                    display_name="Synthetic",
                    quantity=2,
                    unit_price_minor=50,
                    line_total_minor=100,
                )
                | values
            )
        ]
        db.add(order)


def test_catalogue_tenant_composite_key(sessions):
    med = uuid4()
    with sessions.begin() as db:
        for tenant in (uuid4(), uuid4()):
            db.add(
                CatalogueItem(
                    tenant_id=tenant,
                    medication_id=med,
                    display_name="Synthetic",
                    unit_label="demo",
                    unit_price_minor=0,
                    active=True,
                )
            )
    with sessions() as db:
        assert len(db.scalars(select(CatalogueItem)).all()) == 2
