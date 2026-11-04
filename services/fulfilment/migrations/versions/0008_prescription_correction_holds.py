"""Block obsolete prescriptions during a retryable clinic-admin correction."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prescription_correction_holds",
        sa.Column("prescription_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="fulfilment",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM fulfilment.prescription_correction_holds")
    ):
        raise RuntimeError("Prescription correction holds exist; refusing to discard history.")
    op.drop_table("prescription_correction_holds", schema="fulfilment")
