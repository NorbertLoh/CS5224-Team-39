"""B01 payment persistence, isolated from other services.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payments",
        sa.Column("payment_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("appointment_id", sa.Uuid()),
        sa.Column("order_id", sa.Uuid()),
        sa.Column("quote_id", sa.Uuid()),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("resolution", sa.Text(), server_default=sa.text("'none'"), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("commissionable_minor", sa.BigInteger(), nullable=False),
        sa.Column("delivery_fee_minor", sa.BigInteger(), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("commission_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("clinic_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_account_id", sa.Text()),
        sa.Column("provider_checkout_id", sa.Text()),
        sa.Column("provider_payment_id", sa.Text()),
        sa.Column("provider_idempotency_key", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="billing",
    )
    checks = [
        (
            "resource_links",
            "(purpose = 'consultation' AND appointment_id IS NOT NULL "
            "AND order_id IS NULL AND quote_id IS NULL) OR "
            "(purpose = 'medication_delivery' AND appointment_id IS NULL "
            "AND order_id IS NOT NULL AND quote_id IS NOT NULL)",
        ),
        (
            "status",
            "status IN ('pending', 'succeeded', 'failed', "
            "'refund_pending', 'refunded', 'refund_failed')",
        ),
        (
            "resolution",
            "resolution = 'none' OR (resolution = 'refund_required' "
            "AND status IN ('succeeded', 'refund_pending', 'refund_failed'))",
        ),
        ("currency", "currency = 'SGD'"),
        ("total", "amount_minor = commissionable_minor + delivery_fee_minor"),
        ("consultation_fee", "purpose <> 'consultation' OR delivery_fee_minor = 0"),
        ("rate", "commission_bps BETWEEN 0 AND 10000"),
        (
            "commission",
            "commission_amount_minor = "
            "floor(commissionable_minor::numeric * commission_bps / 10000)",
        ),
        ("clinic_amount", "clinic_amount_minor = amount_minor - commission_amount_minor"),
        ("provider", "provider ~ '[^[:space:]]'"),
    ]
    for column in (
        "amount_minor",
        "commissionable_minor",
        "delivery_fee_minor",
        "commission_amount_minor",
        "clinic_amount_minor",
    ):
        checks.append((column, f"{column} BETWEEN 0 AND 9007199254740991"))
    for column in (
        "provider_account_id",
        "provider_checkout_id",
        "provider_payment_id",
        "provider_idempotency_key",
    ):
        checks.append((column, f"{column} IS NULL OR {column} ~ '[^[:space:]]'"))
    for name, condition in checks:
        op.create_check_constraint(f"ck_payments_{name}", "payments", condition, schema="billing")

    for column in ("provider_checkout_id", "provider_payment_id", "provider_idempotency_key"):
        op.create_index(
            f"uq_payments_{column}",
            "payments",
            ["provider", "provider_account_id", column],
            unique=True,
            schema="billing",
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
            postgresql_nulls_not_distinct=True,
        )
    for name, columns in (
        ("patient_page", ["patient_id", "created_at", "payment_id"]),
        ("tenant_page", ["tenant_id", "created_at", "payment_id"]),
        ("appointment", ["appointment_id"]),
        ("order", ["order_id"]),
    ):
        op.create_index(f"ix_payments_{name}", "payments", columns, schema="billing")

    op.execute("""
        CREATE FUNCTION billing.protect_payment() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.payment_id, NEW.tenant_id, NEW.patient_id, NEW.purpose,
                   NEW.appointment_id, NEW.order_id, NEW.quote_id, NEW.currency,
                   NEW.amount_minor, NEW.commissionable_minor, NEW.delivery_fee_minor,
                   NEW.commission_bps, NEW.commission_amount_minor, NEW.clinic_amount_minor)
               IS DISTINCT FROM
               ROW(OLD.payment_id, OLD.tenant_id, OLD.patient_id, OLD.purpose,
                   OLD.appointment_id, OLD.order_id, OLD.quote_id, OLD.currency,
                   OLD.amount_minor, OLD.commissionable_minor, OLD.delivery_fee_minor,
                   OLD.commission_bps, OLD.commission_amount_minor, OLD.clinic_amount_minor)
            THEN
                RAISE EXCEPTION 'Payment ownership and financial snapshots are immutable'
                    USING ERRCODE = '23514';
            END IF;
            NEW.created_at = OLD.created_at;
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_payment BEFORE UPDATE ON billing.payments
        FOR EACH ROW EXECUTE FUNCTION billing.protect_payment()
    """)


def downgrade():
    op.drop_table("payments", schema="billing")
    op.execute("DROP FUNCTION billing.protect_payment()")
