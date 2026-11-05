"""Persist source references and safely skip superseded lifecycle notices."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_lifecycle_emails"
down_revision = "0002_notification_worker"
branch_labels = None
depends_on = None


def constraints(expanded):
    statuses = "'pending', 'sending', 'sent', 'failed', 'uncertain'" + (
        ", 'skipped'" if expanded else ""
    )
    unsent = "'pending', 'sending', 'failed', 'uncertain'" + (", 'skipped'" if expanded else "")
    errors = "'ses_unconfirmed', 'ses_rejected'" + (", 'source_unavailable'" if expanded else "")
    for name in ("ck_jobs_status", "ck_jobs_sent", "ck_jobs_error_code"):
        op.drop_constraint(name, "jobs", schema="notification", type_="check")
    op.create_check_constraint(
        "ck_jobs_status", "jobs", f"status IN ({statuses})", schema="notification"
    )
    op.create_check_constraint(
        "ck_jobs_error_code",
        "jobs",
        f"error_code IS NULL OR error_code IN ({errors})",
        schema="notification",
    )
    op.create_check_constraint(
        "ck_jobs_sent",
        "jobs",
        "(status = 'sent' AND provider_message_id IS NOT NULL AND btrim(provider_message_id) <> '' "
        "AND sent_at IS NOT NULL AND attempts > 0 AND error_code IS NULL) "
        f"OR (status IN ({unsent}) AND provider_message_id IS NULL AND sent_at IS NULL)",
        schema="notification",
    )


def upgrade():
    op.add_column(
        "jobs", sa.Column("source_event", postgresql.JSONB(), nullable=True), schema="notification"
    )
    op.add_column(
        "jobs",
        sa.Column("prepare_attempts", sa.Integer(), nullable=False, server_default="0"),
        schema="notification",
    )
    constraints(True)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM notification.jobs "
            "WHERE status IN ('sending', 'uncertain'))"
        )
    ):
        raise RuntimeError("Resolve sending/uncertain jobs before downgrading notification worker")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM notification.jobs WHERE source_event IS NOT NULL "
            "OR status = 'skipped' OR error_code = 'source_unavailable')"
        )
    ):
        raise RuntimeError("Retain lifecycle migration while lifecycle notification history exists")
    constraints(False)
    op.drop_column("jobs", "prepare_attempts", schema="notification")
    op.drop_column("jobs", "source_event", schema="notification")
