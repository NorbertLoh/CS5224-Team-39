"""Retain clinic-admin correction history and replacement prescription links."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prescription_corrections",
        sa.Column(
            "original_prescription_id",
            sa.Uuid(),
            sa.ForeignKey("clinical_records.prescriptions.prescription_id"),
            primary_key=True,
        ),
        sa.Column(
            "replacement_prescription_id",
            sa.Uuid(),
            sa.ForeignKey("clinical_records.prescriptions.prescription_id"),
            unique=True,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("corrected_by", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="clinical_records",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM clinical_records.prescription_corrections")
    ):
        raise RuntimeError("Prescription corrections exist; refusing to discard history.")
    op.drop_table("prescription_corrections", schema="clinical_records")
