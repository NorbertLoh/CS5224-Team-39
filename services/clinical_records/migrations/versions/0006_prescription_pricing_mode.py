"""Require individual clinic pricing for new and draft prescriptions."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "prescriptions",
        sa.Column("pricing_mode", sa.Text(), nullable=False, server_default="catalogue"),
        schema="clinical_records",
    )
    op.execute(
        "UPDATE clinical_records.prescriptions SET pricing_mode='prescription' WHERE status='draft'"
    )
    op.alter_column(
        "prescriptions", "pricing_mode", server_default="prescription", schema="clinical_records"
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM clinical_records.prescriptions WHERE pricing_mode='prescription'"
        )
    ):
        raise RuntimeError("Prescription-specific pricing exists; refusing to remove its policy.")
    op.drop_column("prescriptions", "pricing_mode", schema="clinical_records")
