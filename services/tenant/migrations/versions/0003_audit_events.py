"""Add tenant-local administrative audit events.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_subject_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("previous_values", JSONB(), nullable=False),
        sa.Column("new_values", JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.clinics.tenant_id"],
            name="fk_audit_events_clinic",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "action IN ('clinic.approved', 'clinic.rejected', 'clinic.suspended', "
            "'clinic.commission_changed')",
            name="ck_audit_events_action",
        ),
        sa.CheckConstraint("reason IS NULL OR btrim(reason) <> ''", name="ck_audit_events_reason"),
        schema="tenant",
    )
    op.create_index(
        "ix_audit_events_tenant_time",
        "audit_events",
        ["tenant_id", "occurred_at", "event_id"],
        schema="tenant",
    )
    op.execute("""
        CREATE FUNCTION tenant.prevent_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Audit events are append-only' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER prevent_audit_mutation BEFORE UPDATE OR DELETE ON tenant.audit_events
        FOR EACH ROW EXECUTE FUNCTION tenant.prevent_audit_mutation()
    """)


def downgrade() -> None:
    op.drop_table("audit_events", schema="tenant")
    op.execute("DROP FUNCTION tenant.prevent_audit_mutation()")
