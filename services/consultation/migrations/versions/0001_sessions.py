"""Service-owned session schema and irreversible lifecycle.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("appointment_id", name="uq_sessions_appointment"),
        sa.CheckConstraint("patient_id <> doctor_id", name="ck_sessions_distinct_participants"),
        sa.CheckConstraint(
            "isfinite(starts_at) AND isfinite(ends_at) AND starts_at < ends_at",
            name="ck_sessions_schedule",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed')", name="ck_sessions_status"
        ),
        sa.CheckConstraint(
            "(status = 'scheduled' AND started_at IS NULL AND ended_at IS NULL) OR "
            "(status = 'in_progress' AND started_at IS NOT NULL AND ended_at IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND ended_at IS NOT NULL)",
            name="ck_sessions_lifecycle",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR (isfinite(started_at) "
            "AND started_at >= starts_at AND started_at < ends_at)",
            name="ck_sessions_start_window",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR (isfinite(ended_at) AND ended_at >= started_at)",
            name="ck_sessions_end_time",
        ),
        schema="consultation",
    )
    op.create_index(
        "ix_sessions_tenant_doctor",
        "sessions",
        ["tenant_id", "doctor_id", "starts_at"],
        schema="consultation",
    )
    op.create_index(
        "ix_sessions_patient", "sessions", ["patient_id", "starts_at"], schema="consultation"
    )
    op.execute("""
        CREATE FUNCTION consultation.guard_session() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'scheduled' THEN
                    RAISE EXCEPTION 'Sessions must begin scheduled' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF ROW(NEW.session_id, NEW.appointment_id, NEW.tenant_id, NEW.patient_id,
                   NEW.doctor_id, NEW.starts_at, NEW.ends_at, NEW.created_at)
               IS DISTINCT FROM
               ROW(OLD.session_id, OLD.appointment_id, OLD.tenant_id, OLD.patient_id,
                   OLD.doctor_id, OLD.starts_at, OLD.ends_at, OLD.created_at) THEN
                RAISE EXCEPTION 'Session context is immutable' USING ERRCODE = '23514';
            END IF;
            IF NOT (NEW.status = OLD.status
                    OR (OLD.status = 'scheduled' AND NEW.status = 'in_progress')
                    OR (OLD.status = 'in_progress' AND NEW.status = 'completed')) THEN
                RAISE EXCEPTION 'Illegal session transition' USING ERRCODE = '23514';
            END IF;
            IF (OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at)
               OR (OLD.ended_at IS NOT NULL AND NEW.ended_at IS DISTINCT FROM OLD.ended_at) THEN
                RAISE EXCEPTION 'Lifecycle times are immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER guard_session BEFORE INSERT OR UPDATE ON consultation.sessions
        FOR EACH ROW EXECUTE FUNCTION consultation.guard_session()
    """)


def downgrade():
    op.drop_table("sessions", schema="consultation")
    op.execute("DROP FUNCTION consultation.guard_session()")
