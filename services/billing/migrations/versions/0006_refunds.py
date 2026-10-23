"""Durable full consultation refund operations and immutable request audit.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refund_attempts",
        sa.Column("refund_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "payment_id", sa.Uuid(), sa.ForeignKey("billing.payments.payment_id"), nullable=False
        ),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_by_name", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("provider_refund_id", sa.Text(), unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text()),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        *(
            sa.Column(
                name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            )
            for name in ("next_attempt_at", "created_at", "updated_at")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'review')", name="ck_refund_status"
        ),
        sa.CheckConstraint("length(trim(reason)) BETWEEN 1 AND 1000", name="ck_refund_reason"),
        schema="billing",
    )
    op.create_index(
        "ix_refund_payment", "refund_attempts", ["payment_id", "created_at"], schema="billing"
    )
    op.create_index(
        "ix_refund_pending", "refund_attempts", ["status", "next_attempt_at"], schema="billing"
    )
    op.create_index(
        "uq_refund_active_payment",
        "refund_attempts",
        ["payment_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
        schema="billing",
    )
    op.execute("""
        CREATE FUNCTION billing.protect_refund() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.refund_id, NEW.payment_id, NEW.requested_by,
                   NEW.requested_by_name, NEW.reason, NEW.created_at)
               IS DISTINCT FROM
               ROW(OLD.refund_id, OLD.payment_id, OLD.requested_by,
                   OLD.requested_by_name, OLD.reason, OLD.created_at)
            THEN
                RAISE EXCEPTION 'Refund request audit is immutable' USING ERRCODE = '23514';
            END IF;
            NEW.updated_at = clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_refund BEFORE UPDATE ON billing.refund_attempts
        FOR EACH ROW EXECUTE FUNCTION billing.protect_refund()
    """)


def downgrade():
    op.drop_table("refund_attempts", schema="billing")
    op.execute("DROP FUNCTION billing.protect_refund()")
