"""Retain cancellation reason and verified actor without changing appointment links.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("cancelled_by_subject_id", sa.Uuid()),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("appointments", column, schema="scheduling")
    # Legacy cancelled rows have no audit fields; preserve them on upgrade.
    op.create_check_constraint(
        "ck_appointments_cancellation_record",
        "appointments",
        "(cancelled_at IS NULL AND cancellation_reason IS NULL "
        "AND cancelled_by_subject_id IS NULL) OR "
        "(status = 'cancelled' AND cancelled_at IS NOT NULL "
        "AND cancelled_by_subject_id IS NOT NULL AND cancellation_reason IS NOT NULL "
        "AND btrim(cancellation_reason) <> '' AND length(cancellation_reason) <= 2000)",
        schema="scheduling",
    )


def downgrade():
    op.drop_constraint("ck_appointments_cancellation_record", "appointments", schema="scheduling")
    for column in ("cancelled_at", "cancelled_by_subject_id", "cancellation_reason"):
        op.drop_column("appointments", column, schema="scheduling")
