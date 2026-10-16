from uuid import uuid4

from sqlalchemy import text


def payment_values(**overrides):
    return {
        "payment_id": uuid4(),
        "tenant_id": uuid4(),
        "patient_id": uuid4(),
        "purpose": "consultation",
        "appointment_id": uuid4(),
        "amount_minor": 2500,
        "currency": "SGD",
        "commissionable_minor": 2500,
        "delivery_fee_minor": 0,
        "commission_bps": 1000,
        "commission_amount_minor": 250,
        "clinic_amount_minor": 2250,
        "provider": "stripe",
    } | overrides


def insert(engine, values):
    columns = ", ".join(values)
    parameters = ", ".join(f":{name}" for name in values)
    with engine.begin() as connection:
        return connection.scalar(
            text(
                f"INSERT INTO billing.payments ({columns}) VALUES ({parameters}) "
                "RETURNING payment_id"
            ),
            values,
        )


def read(engine, payment_id):
    with engine.connect() as connection:
        return (
            connection.execute(
                text("SELECT * FROM billing.payments WHERE payment_id=:id"),
                {"id": payment_id},
            )
            .mappings()
            .one()
        )
