from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.helpers import insert, payment_values, read


def test_orm_stores_consultation_and_fetches_database_defaults(database):
    from app.models import Payment

    values = payment_values()
    del values["payment_id"]
    with Session(database) as session, session.begin():
        row = Payment(**values)
        session.add(row)
        session.flush()
        assert isinstance(row.payment_id, UUID)
        assert row.status == "pending" and row.resolution == "none"
        assert row.created_at.utcoffset() == timedelta(0)
        assert row.updated_at.utcoffset() == timedelta(0)
        payment_id = row.payment_id
    assert read(database, payment_id)["amount_minor"] == 2500


@pytest.mark.parametrize(
    ("subtotal", "delivery", "rate", "commission", "clinic"),
    [
        (2000, 500, 1000, 200, 2300),
        (1, 0, 3333, 0, 1),
        (0, 0, 1000, 0, 0),
        (100, 25, 0, 0, 125),
        (100, 25, 10000, 100, 25),
        (9007199254740991, 0, 10000, 9007199254740991, 0),
        (9007199254740991, 0, 9999, 9006298534815516, 900719925475),
    ],
)
def test_medication_commission_excludes_delivery_and_rounds_down(
    database, subtotal, delivery, rate, commission, clinic
):
    payment_id = insert(
        database,
        payment_values(
            purpose="medication_delivery",
            appointment_id=None,
            order_id=uuid4(),
            quote_id=uuid4(),
            amount_minor=subtotal + delivery,
            commissionable_minor=subtotal,
            delivery_fee_minor=delivery,
            commission_bps=rate,
            commission_amount_minor=commission,
            clinic_amount_minor=clinic,
        ),
    )
    row = read(database, payment_id)
    assert row["commission_amount_minor"] == commission
    assert row["clinic_amount_minor"] == clinic


@pytest.mark.parametrize(
    "overrides",
    [
        {"purpose": "other"},
        {"appointment_id": None},
        {"order_id": uuid4()},
        {"quote_id": uuid4()},
        {"purpose": "medication_delivery"},
        {"purpose": "medication_delivery", "appointment_id": None, "order_id": uuid4()},
        {"status": "paid"},
        {"resolution": "refunded"},
        {"resolution": "refund_required"},
        {"status": "failed", "resolution": "refund_required"},
        {"status": "refunded", "resolution": "refund_required"},
        {"tenant_id": None},
        {"patient_id": None},
        {"currency": "USD"},
        {"amount_minor": -1},
        {"amount_minor": 9007199254740992},
        {"commissionable_minor": -1},
        {"delivery_fee_minor": -1},
        {"commission_amount_minor": -1},
        {"clinic_amount_minor": -1},
        {"commission_bps": -1},
        {"commission_bps": 10001},
        {"commission_amount_minor": 251, "clinic_amount_minor": 2249},
        {"clinic_amount_minor": 2500},
        {"delivery_fee_minor": 1},
        {"provider": " "},
        {"provider_account_id": " "},
        {"provider_checkout_id": " "},
        {"provider_payment_id": " "},
        {"provider_idempotency_key": " "},
    ],
)
def test_invalid_payment_facts_are_rejected_by_database(database, overrides):
    with pytest.raises(IntegrityError):
        insert(database, payment_values(**overrides))


@pytest.mark.parametrize(
    "status", ["pending", "failed", "succeeded", "refund_pending", "refunded", "refund_failed"]
)
def test_contract_statuses_are_storable(database, status):
    payment_id = insert(database, payment_values(status=status))
    assert read(database, payment_id)["status"] == status


@pytest.mark.parametrize("status", ["succeeded", "refund_pending", "refund_failed"])
def test_refund_review_is_separate_from_payment_truth(database, status):
    payment_id = insert(database, payment_values(status=status, resolution="refund_required"))
    assert read(database, payment_id)["resolution"] == "refund_required"


@pytest.mark.parametrize(
    "reference", ["provider_checkout_id", "provider_payment_id", "provider_idempotency_key"]
)
@pytest.mark.parametrize("account", [None, "acct_demo"])
def test_provider_reference_unique_within_account_namespace(database, reference, account):
    reference_value = f"synthetic_{uuid4()}"
    values = {reference: reference_value, "provider_account_id": account}
    insert(database, payment_values(**values))
    with pytest.raises(IntegrityError):
        insert(database, payment_values(**values))
    insert(database, payment_values(**(values | {"provider_account_id": "different_account"})))
    insert(database, payment_values(**(values | {"provider": "different_provider"})))


def test_missing_provider_references_do_not_conflict(database):
    insert(database, payment_values())
    insert(database, payment_values())


def test_failed_retry_and_late_duplicate_success_preserve_history(database):
    original = payment_values(status="failed")
    original_id = insert(database, original)
    newer_id = insert(database, original | {"payment_id": uuid4(), "status": "succeeded"})
    with database.begin() as connection:
        connection.execute(
            text(
                "UPDATE billing.payments SET status='succeeded', resolution='refund_required' "
                "WHERE payment_id=:id"
            ),
            {"id": original_id},
        )
    assert read(database, original_id)["resolution"] == "refund_required"
    assert read(database, newer_id)["status"] == "succeeded"


@pytest.mark.parametrize("method", ["sql", "orm"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("payment_id", uuid4()),
        ("tenant_id", uuid4()),
        ("patient_id", uuid4()),
        ("appointment_id", uuid4()),
        ("purpose", "medication_delivery"),
        ("order_id", uuid4()),
        ("quote_id", uuid4()),
        ("currency", "USD"),
        ("amount_minor", 5000),
        ("commissionable_minor", 5000),
        ("delivery_fee_minor", 1),
        ("commission_bps", 2000),
        ("commission_amount_minor", 500),
        ("clinic_amount_minor", 2000),
    ],
)
def test_ownership_and_snapshots_cannot_be_rewritten(database, method, field, value):
    from app.models import Payment

    payment_id = insert(database, payment_values())
    with pytest.raises(IntegrityError):
        if method == "sql":
            with database.begin() as connection:
                connection.execute(
                    text(f"UPDATE billing.payments SET {field}=:value WHERE payment_id=:id"),
                    {"value": value, "id": payment_id},
                )
        else:
            with Session(database) as session, session.begin():
                row = session.get(Payment, payment_id)
                setattr(row, field, value)
                session.flush()


def test_consistent_financial_rewrite_is_still_rejected(database):
    payment_id = insert(database, payment_values())
    with pytest.raises(IntegrityError):
        with database.begin() as connection:
            connection.execute(
                text(
                    "UPDATE billing.payments SET amount_minor=5000, commissionable_minor=5000, "
                    "commission_amount_minor=500, clinic_amount_minor=4500 WHERE payment_id=:id"
                ),
                {"id": payment_id},
            )


def test_mutable_provider_updates_preserve_creation_and_refresh_update_time(database):
    from app.models import Payment

    payment_id = insert(database, payment_values())
    before = read(database, payment_id)
    with Session(database) as session, session.begin():
        row = session.get(Payment, payment_id)
        row.provider_checkout_id = f"checkout_{uuid4()}"
        session.flush()
        assert row.created_at == before["created_at"]
        assert row.updated_at > before["updated_at"]
    after_orm = read(database, payment_id)
    with database.begin() as connection:
        row = connection.execute(
            text(
                "UPDATE billing.payments SET status='succeeded', created_at='2000-01-01', "
                "updated_at='2000-01-01' WHERE payment_id=:id RETURNING created_at, updated_at"
            ),
            {"id": payment_id},
        ).one()
        assert row.created_at == before["created_at"]
        assert row.updated_at > after_orm["updated_at"]
