"""Allow actual clinical start times outside the booked slot without rewriting history."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_sessions_start_window", "sessions", schema="consultation")
    op.create_check_constraint(
        "ck_sessions_start_window",
        "sessions",
        "started_at IS NULL OR isfinite(started_at)",
        schema="consultation",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM consultation.sessions WHERE started_at IS NOT NULL "
            "AND (started_at < starts_at - test_start_early_minutes * interval '1 minute' "
            "OR started_at >= ends_at))"
        )
    ):
        raise RuntimeError(
            "Out-of-slot clinical starts exist; retain migration 0006 to preserve history"
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
