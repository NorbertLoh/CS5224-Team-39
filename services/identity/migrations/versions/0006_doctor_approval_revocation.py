"""Allow explicit withdrawal of approved doctor eligibility for resubmission."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_doctor_status", "doctor_applications", schema="identity", type_="check")
    op.create_check_constraint(
        "ck_doctor_status",
        "doctor_applications",
        "status IN ('pending','approved','rejected','revoked')",
        schema="identity",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM identity.doctor_applications WHERE status = 'revoked') THEN
            RAISE EXCEPTION 'Revoked doctor applications prevent downgrade';
        END IF;
    END $$""")
    op.drop_constraint("ck_doctor_status", "doctor_applications", schema="identity", type_="check")
    op.create_check_constraint(
        "ck_doctor_status",
        "doctor_applications",
        "status IN ('pending','approved','rejected')",
        schema="identity",
    )
