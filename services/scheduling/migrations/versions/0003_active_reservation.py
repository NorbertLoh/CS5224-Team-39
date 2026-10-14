"""One active PostgreSQL reservation per fixed slot.

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
    # Existing duplicates fail migration; never silently choose a booking to keep.
    op.create_index(
        "uq_appointments_active_slot",
        "appointments",
        ["slot_id"],
        unique=True,
        schema="scheduling",
        postgresql_where=sa.text(
            "status IN ('held', 'pending_payment', 'confirmed', 'in_progress')"
        ),
    )


def downgrade():
    op.drop_index("uq_appointments_active_slot", table_name="appointments", schema="scheduling")
