"""Create C02 clinic persistence.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinics",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("primary_color", sa.Text(), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("consultation_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'SGD'")),
        sa.Column("commission_bps", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.UniqueConstraint("slug", name="uq_clinics_slug"),
        sa.CheckConstraint("btrim(slug) <> ''", name="ck_clinics_slug"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_clinics_name"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'active', 'rejected', 'suspended')",
            name="ck_clinics_status",
        ),
        sa.CheckConstraint("primary_color ~ '^#[0-9A-Fa-f]{6}$'", name="ck_clinics_color"),
        sa.CheckConstraint(
            "logo_url IS NULL OR logo_url ~ '^https://[^[:space:]/?#]+[^[:space:]]*$'",
            name="ck_clinics_logo_url",
        ),
        sa.CheckConstraint(
            "consultation_price_minor BETWEEN 0 AND 9007199254740991",
            name="ck_clinics_price",
        ),
        sa.CheckConstraint("currency = 'SGD'", name="ck_clinics_currency"),
        sa.CheckConstraint("commission_bps BETWEEN 0 AND 10000", name="ck_clinics_commission"),
        sa.CheckConstraint(
            "review_reason IS NULL OR btrim(review_reason) <> ''",
            name="ck_clinics_review_reason",
        ),
        schema="tenant",
    )
    op.create_index(
        "ix_clinics_public_page", "clinics", ["status", "name", "tenant_id"], schema="tenant"
    )
    op.create_index(
        "ix_clinics_admin_page", "clinics", ["status", "created_at", "tenant_id"], schema="tenant"
    )
    op.execute("""
        CREATE FUNCTION tenant.touch_clinic() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.slug IS DISTINCT FROM OLD.slug THEN
                RAISE EXCEPTION 'Clinic slug is immutable' USING ERRCODE = '23514';
            END IF;
            NEW.created_at := OLD.created_at;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER touch_clinic BEFORE UPDATE ON tenant.clinics
        FOR EACH ROW EXECUTE FUNCTION tenant.touch_clinic()
    """)


def downgrade() -> None:
    op.drop_table("clinics", schema="tenant")
    op.execute("DROP FUNCTION tenant.touch_clinic()")
