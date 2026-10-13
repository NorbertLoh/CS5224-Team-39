"""Track retryable creator membership provisioning.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clinics", sa.Column("creator_subject_id", sa.Uuid()), schema="tenant")
    op.add_column(
        "clinics",
        sa.Column(
            "membership_provisioned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        schema="tenant",
    )


def downgrade() -> None:
    op.drop_column("clinics", "membership_provisioned", schema="tenant")
    op.drop_column("clinics", "creator_subject_id", schema="tenant")
