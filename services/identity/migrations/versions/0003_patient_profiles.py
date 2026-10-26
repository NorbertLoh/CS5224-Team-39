"""Persist patients' own contact and delivery address."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "patient_profiles",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.Text(), nullable=False),
        sa.Column("address_line", sa.Text(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text(), nullable=False, server_default=sa.text("'SG'")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("subject_id"),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["identity.subjects.subject_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "phone_number ~ '^\\+65[689][0-9]{7}$'", name="ck_patient_profile_phone"
        ),
        sa.CheckConstraint("btrim(address_line) <> ''", name="ck_patient_profile_address"),
        sa.CheckConstraint("postal_code ~ '^[0-9]{6}$'", name="ck_patient_profile_postal"),
        sa.CheckConstraint("country_code = 'SG'", name="ck_patient_profile_country"),
        schema="identity",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM identity.patient_profiles) THEN
            RAISE EXCEPTION 'Saved patient profiles prevent downgrade';
        END IF;
    END $$""")
    op.drop_table("patient_profiles", schema="identity")
