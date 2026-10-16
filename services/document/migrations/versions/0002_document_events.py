"""P02 inbox and document-ready outbox.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

from app.models import event_inbox, event_outbox

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    event_inbox.create(op.get_bind())
    event_outbox.create(op.get_bind())


def downgrade():
    event_outbox.drop(op.get_bind())
    event_inbox.drop(op.get_bind())
