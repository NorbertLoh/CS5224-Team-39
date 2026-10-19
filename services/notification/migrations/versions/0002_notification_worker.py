"""Durable event intake and explicit send claims/ambiguous outcomes."""

import sqlalchemy as sa
from alembic import op

revision = "0002_notification_worker"
down_revision = "0001_notification_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_inbox",
        sa.Column("consumer", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("detail_type", sa.String(100), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="notification",
    )
    op.add_column(
        "jobs",
        sa.Column("ready_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="notification",
    )
    op.execute("UPDATE notification.jobs SET ready_at = NULL WHERE status IN ('sent', 'failed')")
    op.add_column(
        "jobs", sa.Column("send_started_at", sa.DateTime(timezone=True)), schema="notification"
    )
    for name in ("ck_jobs_status", "ck_jobs_sent", "ck_jobs_error_code"):
        op.drop_constraint(name, "jobs", schema="notification", type_="check")
    op.create_check_constraint(
        "ck_jobs_status",
        "jobs",
        "status IN ('pending', 'sending', 'sent', 'failed', 'uncertain')",
        schema="notification",
    )
    op.create_check_constraint(
        "ck_jobs_sent",
        "jobs",
        "(status = 'sent' AND provider_message_id IS NOT NULL "
        "AND btrim(provider_message_id) <> '' AND sent_at IS NOT NULL "
        "AND attempts > 0 AND error_code IS NULL) "
        "OR (status IN ('pending', 'sending', 'failed', 'uncertain') "
        "AND provider_message_id IS NULL AND sent_at IS NULL)",
        schema="notification",
    )
    op.create_check_constraint(
        "ck_jobs_error_code",
        "jobs",
        "error_code IS NULL OR error_code IN ('ses_unconfirmed', 'ses_rejected')",
        schema="notification",
    )
    op.create_check_constraint(
        "ck_jobs_claim",
        "jobs",
        "status NOT IN ('sending', 'uncertain') OR (send_started_at IS NOT NULL AND attempts > 0)",
        schema="notification",
    )


def downgrade():
    # Ambiguous in-flight work cannot be silently converted into retryable pending jobs.
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notification.jobs "
            "WHERE status IN ('sending', 'uncertain'))"
        )
    ):
        raise RuntimeError("Resolve sending/uncertain jobs before downgrading notification worker")
    for name in ("ck_jobs_status", "ck_jobs_sent", "ck_jobs_error_code", "ck_jobs_claim"):
        op.drop_constraint(name, "jobs", schema="notification", type_="check")
    op.execute(
        "UPDATE notification.jobs SET error_code = 'ses_unconfirmed' "
        "WHERE error_code = 'ses_rejected'"
    )
    op.create_check_constraint(
        "ck_jobs_status", "jobs", "status IN ('pending', 'sent', 'failed')", schema="notification"
    )
    op.create_check_constraint(
        "ck_jobs_sent",
        "jobs",
        "(status = 'sent' AND provider_message_id IS NOT NULL "
        "AND btrim(provider_message_id) <> '' AND sent_at IS NOT NULL "
        "AND attempts > 0 AND error_code IS NULL) "
        "OR (status IN ('pending', 'failed') AND provider_message_id IS NULL AND sent_at IS NULL)",
        schema="notification",
    )
    op.create_check_constraint(
        "ck_jobs_error_code",
        "jobs",
        "error_code IS NULL OR error_code = 'ses_unconfirmed'",
        schema="notification",
    )
    op.drop_column("jobs", "send_started_at", schema="notification")
    op.drop_column("jobs", "ready_at", schema="notification")
    op.drop_table("event_inbox", schema="notification")
