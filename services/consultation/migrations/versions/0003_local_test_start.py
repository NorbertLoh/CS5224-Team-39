"""Persist an explicitly bounded local-test early clinical start allowance."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sessions",
        sa.Column(
            "test_start_early_minutes", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        schema="consultation",
    )
    op.drop_constraint("ck_sessions_start_window", "sessions", schema="consultation")
    op.create_check_constraint(
        "ck_sessions_start_window",
        "sessions",
        "started_at IS NULL OR (isfinite(started_at) "
        "AND started_at >= starts_at - test_start_early_minutes * interval '1 minute' "
        "AND started_at < ends_at)",
        schema="consultation",
    )
    op.create_check_constraint(
        "ck_sessions_test_start_window",
        "sessions",
        "test_start_early_minutes BETWEEN 0 AND 180 "
        "AND (test_start_early_minutes = 0 OR started_at IS NOT NULL)",
        schema="consultation",
    )
    op.execute("""
        CREATE FUNCTION consultation.guard_test_start_window() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.status <> 'scheduled' AND
               NEW.test_start_early_minutes IS DISTINCT FROM OLD.test_start_early_minutes THEN
                RAISE EXCEPTION 'Recorded test start allowance is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER guard_test_start_window BEFORE UPDATE ON consultation.sessions
        FOR EACH ROW EXECUTE FUNCTION consultation.guard_test_start_window()
    """)


def downgrade():
    # Refuse to rewrite actual clinical timestamps to fit the old constraint.
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM consultation.sessions WHERE started_at < starts_at)")
    ):
        raise RuntimeError(
            "Early-start test sessions exist; retain migration 0003 to preserve history"
        )
    op.execute("DROP TRIGGER guard_test_start_window ON consultation.sessions")
    op.execute("DROP FUNCTION consultation.guard_test_start_window()")
    op.drop_constraint("ck_sessions_test_start_window", "sessions", schema="consultation")
    op.drop_constraint("ck_sessions_start_window", "sessions", schema="consultation")
    op.create_check_constraint(
        "ck_sessions_start_window",
        "sessions",
        "started_at IS NULL OR (isfinite(started_at) "
        "AND started_at >= starts_at AND started_at < ends_at)",
        schema="consultation",
    )
    op.drop_column("sessions", "test_start_early_minutes", schema="consultation")
