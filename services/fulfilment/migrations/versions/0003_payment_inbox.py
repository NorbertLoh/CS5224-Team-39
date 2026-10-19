"""Fulfilment-owned medication payment inbox.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_inbox",
        sa.Column("consumer", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("detail_type", sa.String(100), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="fulfilment",
    )


def downgrade():
    op.drop_table("event_inbox", schema="fulfilment")
