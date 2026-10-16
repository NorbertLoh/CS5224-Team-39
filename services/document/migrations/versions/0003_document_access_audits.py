"""P03 durable document access audit.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

from app.models import AccessAudit

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    AccessAudit.__table__.create(op.get_bind())


def downgrade():
    AccessAudit.__table__.drop(op.get_bind())
