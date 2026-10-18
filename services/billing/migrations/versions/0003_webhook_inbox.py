"""Verified Stripe event receipts.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stripe_webhook_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text()),
        sa.Column("api_version", sa.Text()),
        sa.Column("provider_created_at", sa.BigInteger(), nullable=False),
        sa.Column("object_data", JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ignored', 'processed')", name="ck_webhook_status"
        ),
        schema="billing",
    )
    op.create_index(
        "ix_stripe_webhook_pending",
        "stripe_webhook_events",
        ["status", "received_at"],
        schema="billing",
    )


def downgrade():
    op.drop_index("ix_stripe_webhook_pending", schema="billing")
    op.drop_table("stripe_webhook_events", schema="billing")
