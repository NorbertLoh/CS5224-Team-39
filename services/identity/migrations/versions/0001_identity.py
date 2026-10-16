"""Create C02 subjects and clinic memberships.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("cognito_sub", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "global_roles",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.PrimaryKeyConstraint("subject_id"),
        sa.UniqueConstraint("cognito_sub", name="uq_subjects_cognito_sub"),
        sa.CheckConstraint("btrim(cognito_sub) <> ''", name="ck_subjects_cognito_sub"),
        sa.CheckConstraint("btrim(display_name) <> ''", name="ck_subjects_display_name"),
        sa.CheckConstraint(
            """global_roles = ARRAY[]::text[]
            OR global_roles = ARRAY['patient']::text[]
            OR global_roles = ARRAY['platform_admin']::text[]
            OR global_roles = ARRAY['patient', 'platform_admin']::text[]
            OR global_roles = ARRAY['platform_admin', 'patient']::text[]""",
            name="ck_subjects_global_roles",
        ),
        schema="identity",
    )
    op.create_table(
        "memberships",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("membership_id"),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["identity.subjects.subject_id"],
            name="fk_memberships_subject",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("subject_id", "tenant_id", name="uq_memberships_subject_tenant"),
        sa.CheckConstraint(
            """roles = ARRAY['doctor']::text[]
            OR roles = ARRAY['clinic_admin']::text[]
            OR roles = ARRAY['doctor', 'clinic_admin']::text[]
            OR roles = ARRAY['clinic_admin', 'doctor']::text[]""",
            name="ck_memberships_roles",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_memberships_status"),
        schema="identity",
    )
    op.create_index(
        "ix_memberships_tenant_page",
        "memberships",
        ["tenant_id", "created_at", "membership_id"],
        schema="identity",
    )
    # Keep timestamps correct for both ORM writes and operator SQL updates.
    op.execute("""
        CREATE FUNCTION identity.touch_membership() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.created_at := OLD.created_at;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER touch_membership BEFORE UPDATE ON identity.memberships
        FOR EACH ROW EXECUTE FUNCTION identity.touch_membership()
    """)


def downgrade() -> None:
    op.drop_table("memberships", schema="identity")
    op.execute("DROP FUNCTION identity.touch_membership()")
    op.drop_table("subjects", schema="identity")
