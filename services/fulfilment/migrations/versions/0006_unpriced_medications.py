"""Allow typed medicines to await clinic-admin pricing."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "catalogue_items",
        "unit_price_minor",
        existing_type=sa.BigInteger(),
        nullable=True,
        schema="fulfilment",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM fulfilment.catalogue_items WHERE unit_price_minor IS NULL")
    ):
        raise RuntimeError("Price unpriced medications before downgrading; no price is fabricated.")
    op.alter_column(
        "catalogue_items",
        "unit_price_minor",
        existing_type=sa.BigInteger(),
        nullable=False,
        schema="fulfilment",
    )
