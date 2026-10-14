"""Add optional normalized email for existing account assignment."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subjects", sa.Column("email", sa.Text(), nullable=True), schema="identity")
    op.create_unique_constraint("uq_subjects_email", "subjects", ["email"], schema="identity")
    op.create_check_constraint(
        "ck_subjects_email",
        "subjects",
        "email IS NULL OR (email = lower(btrim(email)) AND email <> '')",
        schema="identity",
    )


def downgrade() -> None:
    op.drop_constraint("ck_subjects_email", "subjects", schema="identity")
    op.drop_constraint("uq_subjects_email", "subjects", schema="identity")
    op.drop_column("subjects", "email", schema="identity")
