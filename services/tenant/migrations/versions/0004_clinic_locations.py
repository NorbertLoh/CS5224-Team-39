"""Save clinic pickup locations and their audit trail."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clinic_locations",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("location", JSONB(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.clinics.tenant_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("jsonb_typeof(location) = 'object'", name="ck_clinic_locations_object"),
        schema="tenant",
    )
    op.drop_constraint("ck_audit_events_action", "audit_events", schema="tenant")
    op.create_check_constraint(
        "ck_audit_events_action",
        "audit_events",
        "action IN ('clinic.approved', 'clinic.rejected', 'clinic.suspended', "
        "'clinic.commission_changed', 'clinic.location_changed')",
        schema="tenant",
    )


def downgrade():
    # Preserve the append-only correction history instead of silently discarding it.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM tenant.audit_events WHERE action='clinic.location_changed') THEN
            RAISE EXCEPTION 'Clinic location audit history prevents downgrade';
        END IF;
    END $$""")
    op.drop_table("clinic_locations", schema="tenant")
    op.drop_constraint("ck_audit_events_action", "audit_events", schema="tenant")
    op.create_check_constraint(
        "ck_audit_events_action",
        "audit_events",
        "action IN ('clinic.approved', 'clinic.rejected', 'clinic.suspended', "
        "'clinic.commission_changed')",
        schema="tenant",
    )
