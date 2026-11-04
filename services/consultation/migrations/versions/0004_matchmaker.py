"""Database-backed signalling ownership. Existing single-node admissions stay valid.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signalling_nodes",
        sa.Column("node_id", sa.Uuid(), primary_key=True),
        sa.Column("token_digest", sa.Text(), nullable=False),
        sa.Column("internal_url", sa.Text(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("draining", sa.Boolean(), nullable=False),
        schema="consultation",
    )
    op.create_table(
        "room_assignments",
        sa.Column("session_id", sa.Uuid(), primary_key=True),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["consultation.sessions.session_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["node_id"], ["consultation.signalling_nodes.node_id"]),
        sa.CheckConstraint("version > 0", name="ck_room_assignment_version"),
        schema="consultation",
    )
    op.create_index(
        "ix_room_assignment_node", "room_assignments", ["node_id"], schema="consultation"
    )
    op.add_column("admissions", sa.Column("node_id", sa.Uuid()), schema="consultation")
    op.add_column(
        "admissions", sa.Column("assignment_version", sa.Integer()), schema="consultation"
    )


def downgrade():
    # Explicit rollback revokes bound credentials; they must never become unbound.
    op.execute("DELETE FROM consultation.admissions WHERE node_id IS NOT NULL")
    op.drop_column("admissions", "assignment_version", schema="consultation")
    op.drop_column("admissions", "node_id", schema="consultation")
    op.drop_table("room_assignments", schema="consultation")
    op.drop_table("signalling_nodes", schema="consultation")
