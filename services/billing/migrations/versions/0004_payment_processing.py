"""Payment success outbox and retryable receipt processing.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from telelink_common.outbox import outbox_table

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    outbox_table(sa.MetaData(schema="billing")).create(op.get_bind())
    for column in (
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("stripe_webhook_events", column, schema="billing")
    op.drop_constraint("ck_webhook_status", "stripe_webhook_events", schema="billing")
    op.create_check_constraint(
        "ck_webhook_status",
        "stripe_webhook_events",
        "status IN ('pending', 'ignored', 'processed', 'rejected')",
        schema="billing",
    )
    op.drop_index("ix_stripe_webhook_pending", schema="billing")
    op.create_index(
        "ix_stripe_webhook_pending",
        "stripe_webhook_events",
        ["status", "next_attempt_at", "received_at"],
        schema="billing",
    )


def downgrade():
    # Preserve receipts when returning to B03, which has no rejected state.
    op.execute("UPDATE billing.stripe_webhook_events SET status='ignored' WHERE status='rejected'")
    op.drop_constraint("ck_webhook_status", "stripe_webhook_events", schema="billing")
    op.create_check_constraint(
        "ck_webhook_status",
        "stripe_webhook_events",
        "status IN ('pending', 'ignored', 'processed')",
        schema="billing",
    )
    op.drop_index("ix_stripe_webhook_pending", schema="billing")
    op.create_index(
        "ix_stripe_webhook_pending",
        "stripe_webhook_events",
        ["status", "received_at"],
        schema="billing",
    )
    for column in ("processed_at", "next_attempt_at", "last_error", "attempts"):
        op.drop_column("stripe_webhook_events", column, schema="billing")
    op.drop_table("event_outbox", schema="billing")
