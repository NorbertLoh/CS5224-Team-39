"""Create service-owned clinical notes and prescriptions.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
SCHEMA = "clinical_records"


def context_columns():
    return [
        sa.Column(name, sa.Uuid(), nullable=False)
        for name in ("tenant_id", "appointment_id", "patient_id", "doctor_id")
    ] + [
        sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("note_id", sa.Uuid(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        *context_columns(),
        sa.UniqueConstraint("appointment_id", name="uq_notes_appointment"),
        sa.CheckConstraint("btrim(text) <> ''", name="ck_notes_text"),
        schema=SCHEMA,
    )
    op.create_table(
        "prescriptions",
        sa.Column("prescription_id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        *context_columns(),
        sa.CheckConstraint(
            "status IN ('draft', 'issued', 'voided')", name="ck_prescriptions_status"
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND issued_at IS NULL) OR "
            "(status = 'issued' AND issued_at IS NOT NULL) OR status = 'voided'",
            name="ck_prescriptions_issued_at",
        ),
        sa.CheckConstraint(
            "issued_at IS NULL OR (isfinite(issued_at) AND issued_at >= created_at)",
            name="ck_prescriptions_issued_time",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "prescription_items",
        sa.Column("prescription_item_id", sa.Uuid(), primary_key=True),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["clinical_records.prescriptions.prescription_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_prescription_items_quantity"),
        sa.CheckConstraint("btrim(instructions) <> ''", name="ck_prescription_items_instructions"),
        sa.CheckConstraint("btrim(display_name) <> ''", name="ck_prescription_items_display_name"),
        schema=SCHEMA,
    )
    for name, table, columns in (
        ("ix_notes_patient_page", "notes", ["patient_id", "created_at", "note_id"]),
        ("ix_notes_tenant_doctor", "notes", ["tenant_id", "doctor_id", "appointment_id"]),
        (
            "ix_prescriptions_patient_page",
            "prescriptions",
            ["patient_id", "created_at", "prescription_id"],
        ),
        (
            "ix_prescriptions_tenant_doctor_page",
            "prescriptions",
            ["tenant_id", "doctor_id", "created_at", "prescription_id"],
        ),
        (
            "ix_prescriptions_appointment_page",
            "prescriptions",
            ["appointment_id", "created_at", "prescription_id"],
        ),
        (
            "ix_prescription_items_parent",
            "prescription_items",
            ["prescription_id", "prescription_item_id"],
        ),
    ):
        op.create_index(name, table, columns, schema=SCHEMA)
    op.create_index(
        "uq_prescriptions_live_appointment",
        "prescriptions",
        ["appointment_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'voided'"),
        schema=SCHEMA,
    )
    op.execute("""
        CREATE FUNCTION clinical_records.touch_record() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.created_at := OLD.created_at;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    for table in ("notes", "prescriptions"):
        op.execute(f"""
            CREATE TRIGGER touch_record BEFORE UPDATE ON clinical_records.{table}
            FOR EACH ROW EXECUTE FUNCTION clinical_records.touch_record()
        """)


def downgrade() -> None:
    op.drop_table("prescription_items", schema=SCHEMA)
    op.drop_table("prescriptions", schema=SCHEMA)
    op.drop_table("notes", schema=SCHEMA)
    op.execute("DROP FUNCTION clinical_records.touch_record()")
