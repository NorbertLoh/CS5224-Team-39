"""Create fixed slots and appointments

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "availability_slots",
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        postgresql.ExcludeConstraint(
            (sa.column("doctor_id"), "="),
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            using="gist",
            name="ex_slots_doctor_overlap",
        ),
        sa.CheckConstraint("ends_at = starts_at + interval '30 minutes'", name="ck_slots_duration"),
        sa.CheckConstraint("isfinite(starts_at) AND isfinite(ends_at)", name="ck_slots_finite"),
        sa.PrimaryKeyConstraint("slot_id"),
        sa.UniqueConstraint(
            "slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at", name="uq_slots_context"
        ),
        schema="scheduling",
    )
    op.create_index(
        "ix_slots_tenant_doctor_time",
        "availability_slots",
        ["tenant_id", "doctor_id", "starts_at", "slot_id"],
        unique=False,
        schema="scheduling",
    )
    op.create_index(
        "ix_slots_tenant_time",
        "availability_slots",
        ["tenant_id", "starts_at", "slot_id"],
        unique=False,
        schema="scheduling",
    )
    op.create_table(
        "appointments",
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("slot_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'held'"), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultation_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), server_default=sa.text("'SGD'"), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payment_resolution", sa.Text(), server_default=sa.text("'none'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("currency = 'SGD'", name="ck_appointments_currency"),
        sa.CheckConstraint(
            "hold_expires_at IS NULL OR (hold_expires_at > created_at "
            "AND hold_expires_at <= starts_at "
            "AND hold_expires_at <= created_at + interval '10 minutes')",
            name="ck_appointments_hold_deadline",
        ),
        sa.CheckConstraint(
            "payment_resolution IN ('none', 'awaiting_payment', 'confirmed', "
            "'refund_required', 'refunded')",
            name="ck_appointments_payment_resolution",
        ),
        sa.CheckConstraint(
            "status IN ('held', 'pending_payment', 'confirmed', 'in_progress', "
            "'completed', 'expired', 'cancelled', 'no_show')",
            name="ck_appointments_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('confirmed', 'in_progress', 'completed', 'no_show') "
            "OR hold_expires_at IS NULL",
            name="ck_appointments_confirmed_hold",
        ),
        sa.CheckConstraint(
            "status NOT IN ('held', 'pending_payment', 'expired') OR hold_expires_at IS NOT NULL",
            name="ck_appointments_hold_required",
        ),
        sa.CheckConstraint(
            "consultation_price_minor BETWEEN 0 AND 9007199254740991", name="ck_appointments_price"
        ),
        sa.ForeignKeyConstraint(
            ["slot_id", "tenant_id", "doctor_id", "starts_at", "ends_at"],
            [
                "scheduling.availability_slots.slot_id",
                "scheduling.availability_slots.tenant_id",
                "scheduling.availability_slots.doctor_id",
                "scheduling.availability_slots.starts_at",
                "scheduling.availability_slots.ends_at",
            ],
            name="fk_appointments_slot_context",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("appointment_id"),
        schema="scheduling",
    )
    op.create_index(
        "ix_appointments_doctor_time",
        "appointments",
        ["doctor_id", "starts_at", "appointment_id"],
        unique=False,
        schema="scheduling",
    )
    op.create_index(
        "ix_appointments_expiry",
        "appointments",
        ["hold_expires_at", "appointment_id"],
        unique=False,
        schema="scheduling",
        postgresql_where=sa.text("status IN ('held', 'pending_payment')"),
    )
    op.create_index(
        "ix_appointments_patient_time",
        "appointments",
        ["patient_id", "starts_at", "appointment_id"],
        unique=False,
        schema="scheduling",
    )
    op.create_index(
        "ix_appointments_slot", "appointments", ["slot_id"], unique=False, schema="scheduling"
    )
    op.create_index(
        "ix_appointments_tenant_time",
        "appointments",
        ["tenant_id", "starts_at", "appointment_id"],
        unique=False,
        schema="scheduling",
    )
    op.execute("""
        CREATE FUNCTION scheduling.protect_slot() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.slot_id, NEW.tenant_id, NEW.doctor_id, NEW.starts_at, NEW.ends_at)
               IS DISTINCT FROM
               ROW(OLD.slot_id, OLD.tenant_id, OLD.doctor_id, OLD.starts_at, OLD.ends_at) THEN
                RAISE EXCEPTION 'Slot context is immutable' USING ERRCODE = '23514';
            END IF;
            NEW.created_at := OLD.created_at;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_slot BEFORE UPDATE ON scheduling.availability_slots
        FOR EACH ROW EXECUTE FUNCTION scheduling.protect_slot()
    """)
    op.execute("""
        CREATE FUNCTION scheduling.protect_appointment() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF ROW(NEW.appointment_id, NEW.tenant_id, NEW.patient_id, NEW.doctor_id,
                   NEW.slot_id, NEW.starts_at, NEW.ends_at,
                   NEW.consultation_price_minor, NEW.currency)
               IS DISTINCT FROM
               ROW(OLD.appointment_id, OLD.tenant_id, OLD.patient_id, OLD.doctor_id,
                   OLD.slot_id, OLD.starts_at, OLD.ends_at,
                   OLD.consultation_price_minor, OLD.currency) THEN
                RAISE EXCEPTION 'Appointment context and price are immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.hold_expires_at IS NOT NULL AND
               NEW.hold_expires_at IS DISTINCT FROM OLD.hold_expires_at THEN
                RAISE EXCEPTION 'Hold deadline is immutable' USING ERRCODE = '23514';
            END IF;
            NEW.created_at := OLD.created_at;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_appointment BEFORE UPDATE ON scheduling.appointments
        FOR EACH ROW EXECUTE FUNCTION scheduling.protect_appointment()
    """)


def downgrade() -> None:
    op.drop_index("ix_appointments_tenant_time", table_name="appointments", schema="scheduling")
    op.drop_index("ix_appointments_slot", table_name="appointments", schema="scheduling")
    op.drop_index("ix_appointments_patient_time", table_name="appointments", schema="scheduling")
    op.drop_index(
        "ix_appointments_expiry",
        table_name="appointments",
        schema="scheduling",
        postgresql_where=sa.text("status IN ('held', 'pending_payment')"),
    )
    op.drop_index("ix_appointments_doctor_time", table_name="appointments", schema="scheduling")
    op.drop_table("appointments", schema="scheduling")
    op.drop_index("ix_slots_tenant_time", table_name="availability_slots", schema="scheduling")
    op.drop_index(
        "ix_slots_tenant_doctor_time", table_name="availability_slots", schema="scheduling"
    )
    op.drop_table("availability_slots", schema="scheduling")
    op.execute("DROP FUNCTION scheduling.protect_appointment()")
    op.execute("DROP FUNCTION scheduling.protect_slot()")
