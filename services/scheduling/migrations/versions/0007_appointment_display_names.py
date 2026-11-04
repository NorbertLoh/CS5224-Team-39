"""Snapshot patient, doctor and clinic display names on new appointments.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

COLUMNS = ("patient_name", "doctor_name", "clinic_name")


def upgrade():
    # Nullable: appointments booked before this revision keep showing identifiers.
    for name in COLUMNS:
        op.add_column("appointments", sa.Column(name, sa.Text()), schema="scheduling")


def downgrade():
    for name in reversed(COLUMNS):
        op.drop_column("appointments", name, schema="scheduling")
