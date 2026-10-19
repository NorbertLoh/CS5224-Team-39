"""Create notification jobs. Schema and role must be provisioned by an operator."""

import sqlalchemy as sa
from alembic import op

revision = "0001_notification_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_id", sa.Text()),
        sa.Column("error_code", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "event_id", "recipient_id", "template", name="uq_jobs_event_recipient_template"
        ),
        sa.CheckConstraint(
            "template IN ('booking_confirmed', 'document_ready', 'delivery_updated')",
            name="ck_jobs_template",
        ),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_jobs_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts"),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code = 'ses_unconfirmed'", name="ck_jobs_error_code"
        ),
        sa.CheckConstraint(
            "length(btrim(recipient_email)) BETWEEN 3 AND 254 "
            "AND position(chr(10) in recipient_email) = 0 "
            "AND position(chr(13) in recipient_email) = 0",
            name="ck_jobs_email",
        ),
        sa.CheckConstraint(
            "(status = 'sent' AND provider_message_id IS NOT NULL "
            "AND btrim(provider_message_id) <> '' AND sent_at IS NOT NULL "
            "AND attempts > 0 AND error_code IS NULL) "
            "OR (status IN ('pending', 'failed') AND provider_message_id IS NULL "
            "AND sent_at IS NULL)",
            name="ck_jobs_sent",
        ),
        schema="notification",
    )
    op.create_index(
        "ix_jobs_status_created", "jobs", ["status", "created_at"], schema="notification"
    )


def downgrade():
    op.drop_table("jobs", schema="notification")
