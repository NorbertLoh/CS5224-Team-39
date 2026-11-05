"""Store public doctor portraits separately from private supporting documents."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "doctor_photos",
        sa.Column("subject_id", sa.Uuid(), primary_key=True),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["identity.subjects.subject_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "octet_length(content) BETWEEN 1 AND 2097152", name="ck_doctor_photo_size"
        ),
        schema="identity",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM identity.doctor_photos) THEN
            RAISE EXCEPTION 'Stored doctor photos prevent downgrade';
        END IF;
    END $$""")
    op.drop_table("doctor_photos", schema="identity")
