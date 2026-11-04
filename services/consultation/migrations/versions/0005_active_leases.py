"""Renewable active leases with immutable join deadlines.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("active_expires_at", "call_expires_at"):
        op.add_column(
            "admissions", sa.Column(column, sa.DateTime(timezone=True)), schema="consultation"
        )
    # Existing credentials retain their original TURN and admission deadlines.
    op.execute(
        "UPDATE consultation.admissions SET call_expires_at = expires_at, "
        "active_expires_at = CASE WHEN consumed_at IS NOT NULL THEN expires_at END"
    )
    op.create_check_constraint(
        "ck_admissions_call_expiry",
        "admissions",
        "call_expires_at IS NULL OR (isfinite(call_expires_at) "
        "AND call_expires_at >= expires_at "
        "AND call_expires_at <= issued_at + interval '12 hours')",
        schema="consultation",
    )
    op.create_check_constraint(
        "ck_admissions_active_expiry",
        "admissions",
        "active_expires_at IS NULL OR (consumed_at IS NOT NULL "
        "AND isfinite(active_expires_at) AND active_expires_at > consumed_at "
        "AND call_expires_at IS NOT NULL AND active_expires_at <= call_expires_at)",
        schema="consultation",
    )


def downgrade():
    # A pre-renewal runtime cannot enforce extended leases. Revoke those grants.
    op.execute("DELETE FROM consultation.admissions WHERE active_expires_at > expires_at")
    op.drop_constraint("ck_admissions_active_expiry", "admissions", schema="consultation")
    op.drop_constraint("ck_admissions_call_expiry", "admissions", schema="consultation")
    op.drop_column("admissions", "active_expires_at", schema="consultation")
    op.drop_column("admissions", "call_expires_at", schema="consultation")
