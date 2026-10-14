"""Transactional scheduling inbox and confirmation outbox.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from telelink_common.inbox import inbox_table
from telelink_common.outbox import outbox_table

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData(schema="scheduling")
    inbox_table(metadata).create(op.get_bind())
    outbox_table(metadata).create(op.get_bind())


def downgrade():
    op.drop_table("event_outbox", schema="scheduling")
    op.drop_table("event_inbox", schema="scheduling")
