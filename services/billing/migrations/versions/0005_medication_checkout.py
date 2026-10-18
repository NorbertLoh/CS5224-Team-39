"""Durable medication checkout reservation and request-key snapshots.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "medication_checkout_attempts",
        sa.Column("payment_id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("quote_expires_at", sa.DateTime(timezone=True)),
        sa.Column("reservation", JSONB()),
        sa.Column("provider_fields", JSONB()),
        sa.Column("response", JSONB()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolution_requested_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="billing",
    )
    op.create_index(
        "uq_medication_checkout_open_order",
        "medication_checkout_attempts",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
        schema="billing",
    )
    op.create_table(
        "medication_checkout_keys",
        sa.Column("patient_id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column(
            "payment_id",
            sa.Uuid(),
            sa.ForeignKey("billing.medication_checkout_attempts.payment_id", ondelete="CASCADE"),
            nullable=False,
        ),
        schema="billing",
    )


def downgrade():
    op.drop_table("medication_checkout_keys", schema="billing")
    op.drop_table("medication_checkout_attempts", schema="billing")
