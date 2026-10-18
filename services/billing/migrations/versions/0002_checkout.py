"""Durable consultation checkout operations and request key aliases.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "checkout_attempts",
        sa.Column("payment_id", sa.Uuid(), primary_key=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True)),
        sa.Column("provider_fields", JSONB()),
        sa.Column("response", JSONB()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="billing",
    )
    op.create_index(
        "ix_billing_checkout_attempts_appointment_id",
        "checkout_attempts",
        ["appointment_id"],
        schema="billing",
    )
    op.create_table(
        "checkout_keys",
        sa.Column("patient_id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("billing.checkout_attempts.payment_id", ondelete="CASCADE"),
            nullable=False,
        ),
        schema="billing",
    )


def downgrade():
    op.drop_table("checkout_keys", schema="billing")
    op.drop_index("ix_billing_checkout_attempts_appointment_id", schema="billing")
    op.drop_table("checkout_attempts", schema="billing")
