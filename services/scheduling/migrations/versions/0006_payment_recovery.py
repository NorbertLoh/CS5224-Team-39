"""Durable late-payment decisions and billing exception delivery.

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
        "payment_recoveries",
        sa.Column("payment_id", sa.Uuid(), primary_key=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.Text(), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "outcome IN ('recovered', 'refund_required')", name="ck_recovery_outcome"
        ),
        sa.CheckConstraint(
            "reason IN ('late_payment', 'slot_reallocated', 'appointment_cancelled', "
            "'appointment_unavailable', 'duplicate_charge')",
            name="ck_recovery_reason",
        ),
        schema="scheduling",
    )
    op.create_index(
        "ix_recovery_pending",
        "payment_recoveries",
        ["delivered_at", "created_at"],
        schema="scheduling",
    )


def downgrade():
    op.drop_table("payment_recoveries", schema="scheduling")
