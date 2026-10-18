"""Persistent bounded, single-use admission leases.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_sessions_tenant", "sessions", ["session_id", "tenant_id"], schema="consultation"
    )
    op.create_table(
        "admissions",
        sa.Column("session_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("subject_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.Text(), nullable=False),
        sa.Column("peer_id", sa.Uuid(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["session_id", "tenant_id"],
            ["consultation.sessions.session_id", "consultation.sessions.tenant_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_digest", name="uq_admissions_digest"),
        sa.UniqueConstraint("peer_id", name="uq_admissions_peer"),
        sa.CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_admissions_digest"),
        sa.CheckConstraint(
            "isfinite(expires_at) AND expires_at > issued_at "
            "AND expires_at <= issued_at + interval '300 seconds'",
            name="ck_admissions_expiry",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR (consumed_at >= issued_at AND consumed_at < expires_at)",
            name="ck_admissions_consumed",
        ),
        sa.CheckConstraint(
            "released_at IS NULL OR (consumed_at IS NOT NULL AND released_at >= consumed_at)",
            name="ck_admissions_released",
        ),
        schema="consultation",
    )


def downgrade():
    op.drop_table("admissions", schema="consultation")
    op.drop_constraint("uq_sessions_tenant", "sessions", schema="consultation")
