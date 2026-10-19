"""Appointment MC drafts and sealed completion decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
SCHEMA = "clinical_records"


def upgrade():
    op.alter_column("service_read_audits", "prescription_id", nullable=True, schema=SCHEMA)
    op.add_column(
        "service_read_audits", sa.Column("medical_certificate_id", sa.Uuid()), schema=SCHEMA
    )
    op.create_check_constraint(
        "ck_service_read_source",
        "service_read_audits",
        "(prescription_id IS NOT NULL AND medical_certificate_id IS NULL) OR "
        "(prescription_id IS NULL AND medical_certificate_id IS NOT NULL)",
        schema=SCHEMA,
    )
    op.create_table(
        "medical_certificates",
        sa.Column("medical_certificate_id", sa.Uuid(), primary_key=True),
        *[
            sa.Column(name, sa.Uuid(), nullable=False)
            for name in ("tenant_id", "appointment_id", "patient_id", "doctor_id")
        ],
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("start_date", sa.Date()),
        sa.Column("duration_days", sa.Integer()),
        sa.Column("additional_notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("consultation_date", sa.Date()),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("appointment_id", name="uq_mc_appointment"),
        sa.CheckConstraint("duration_days IS NULL OR duration_days > 0", name="ck_mc_duration"),
        sa.CheckConstraint(
            "NOT selected OR (start_date IS NOT NULL AND duration_days IS NOT NULL)",
            name="ck_mc_selected_period",
        ),
        sa.CheckConstraint(
            "(finalized_at IS NULL AND issued_at IS NULL AND consultation_date IS NULL) OR "
            "(finalized_at IS NOT NULL AND consultation_date IS NOT NULL AND "
            "((selected AND issued_at IS NOT NULL) OR (NOT selected AND issued_at IS NULL)))",
            name="ck_mc_finalization",
        ),
        schema=SCHEMA,
    )
    op.execute("""
        CREATE FUNCTION clinical_records.protect_mc() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.finalized_at IS NOT NULL THEN
                RAISE EXCEPTION 'Finalized medical certificate is immutable';
            END IF;
            NEW.created_at := OLD.created_at;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER protect_mc BEFORE UPDATE ON clinical_records.medical_certificates
        FOR EACH ROW EXECUTE FUNCTION clinical_records.protect_mc()
    """)
    op.drop_constraint("ck_read_audit_type", "read_audits", schema=SCHEMA)
    op.create_check_constraint(
        "ck_read_audit_type",
        "read_audits",
        "resource_type IN ('note', 'prescription', 'prescription_list', 'medical_certificate')",
        schema=SCHEMA,
    )


def downgrade():
    op.drop_constraint("ck_service_read_source", "service_read_audits", schema=SCHEMA)
    op.execute("DELETE FROM clinical_records.service_read_audits WHERE prescription_id IS NULL")
    op.drop_column("service_read_audits", "medical_certificate_id", schema=SCHEMA)
    op.alter_column("service_read_audits", "prescription_id", nullable=False, schema=SCHEMA)
    op.execute(
        "DELETE FROM clinical_records.read_audits WHERE resource_type = 'medical_certificate'"
    )
    op.drop_constraint("ck_read_audit_type", "read_audits", schema=SCHEMA)
    op.create_check_constraint(
        "ck_read_audit_type",
        "read_audits",
        "resource_type IN ('note', 'prescription', 'prescription_list')",
        schema=SCHEMA,
    )
    op.drop_table("medical_certificates", schema=SCHEMA)
    op.execute("DROP FUNCTION clinical_records.protect_mc()")
