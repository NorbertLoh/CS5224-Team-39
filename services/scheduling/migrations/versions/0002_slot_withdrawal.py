"""Retain slot history when availability is withdrawn.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "availability_slots",
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        schema="scheduling",
    )
    op.drop_constraint("ex_slots_doctor_overlap", "availability_slots", schema="scheduling")
    op.execute("""
        ALTER TABLE scheduling.availability_slots ADD CONSTRAINT ex_slots_doctor_overlap
        EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
        WHERE (withdrawn_at IS NULL)
    """)


def downgrade():
    # Never delete history to make rollback fit the old overlap constraint.
    # If replacement slots overlap withdrawn slots, rollback fails atomically.
    op.drop_constraint("ex_slots_doctor_overlap", "availability_slots", schema="scheduling")
    op.execute("""
        ALTER TABLE scheduling.availability_slots ADD CONSTRAINT ex_slots_doctor_overlap
        EXCLUDE USING gist (doctor_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
    """)
    op.drop_column("availability_slots", "withdrawn_at", schema="scheduling")
