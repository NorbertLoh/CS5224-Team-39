"""Service-owned transactional prescription event outbox."""

import sqlalchemy as sa
from alembic import op
from telelink_common.outbox import outbox_table

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    outbox_table(sa.MetaData(schema="clinical_records")).create(op.get_bind())


def downgrade():
    op.drop_table("event_outbox", schema="clinical_records")
