"""Durable metadata-only clinical read audit trail."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "read_audits",
        sa.Column("audit_id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid()),
        sa.Column("appointment_id", sa.Uuid()),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "resource_type IN ('note', 'prescription', 'prescription_list')",
            name="ck_read_audit_type",
        ),
        schema="clinical_records",
    )
    op.create_index(
        "ix_read_audits_actor_time",
        "read_audits",
        ["actor_id", "created_at"],
        schema="clinical_records",
    )


def downgrade():
    op.drop_table("read_audits", schema="clinical_records")
