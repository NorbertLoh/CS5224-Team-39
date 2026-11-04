"""Private doctor applications and review audit. Existing assignments are unverified."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "doctor_documents",
        sa.Column("document_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "octet_length(content) BETWEEN 1 AND 5242880", name="ck_doctor_doc_size"
        ),
        schema="identity",
    )
    op.create_index(
        "ix_identity_doctor_documents_subject_id",
        "doctor_documents",
        ["subject_id"],
        schema="identity",
    )
    op.create_table(
        "doctor_applications",
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("licence_number", sa.Text(), nullable=False),
        sa.Column("licensing_authority", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("identity.doctor_documents.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewer_id", sa.Uuid()),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_doctor_status"),
        sa.CheckConstraint("revision > 0", name="ck_doctor_revision"),
        schema="identity",
    )
    op.create_table(
        "doctor_application_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subject_id",
            sa.Uuid(),
            sa.ForeignKey("identity.subjects.subject_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="identity",
    )
    op.create_index(
        "ix_identity_doctor_application_events_subject_id",
        "doctor_application_events",
        ["subject_id"],
        schema="identity",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM identity.doctor_documents)
           OR EXISTS (SELECT 1 FROM identity.doctor_applications)
           OR EXISTS (SELECT 1 FROM identity.doctor_application_events) THEN
            RAISE EXCEPTION 'Doctor verification evidence prevents downgrade';
        END IF;
    END $$""")
    op.drop_table("doctor_application_events", schema="identity")
    op.drop_table("doctor_applications", schema="identity")
    op.drop_table("doctor_documents", schema="identity")
