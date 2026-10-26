"""Store clinic-entered prices separately for each prescription."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("pricing_mode", sa.String(20), nullable=False, server_default="catalogue"),
        schema="fulfilment",
    )
    op.create_table(
        "prescription_prices",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("prescription_id", sa.Uuid(), primary_key=True),
        sa.Column("prescription_item_id", sa.Uuid(), primary_key=True),
        sa.Column("medication_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("priced_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("unit_price_minor BETWEEN 0 AND 9007199254740991", name="ck_rx_price"),
        sa.CheckConstraint("quantity > 0", name="ck_rx_price_quantity"),
        schema="fulfilment",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM fulfilment.prescription_prices")
    ) or op.get_bind().scalar(
        sa.text("SELECT count(*) FROM fulfilment.orders WHERE pricing_mode='prescription'")
    ):
        raise RuntimeError("Prescription pricing exists; refusing to remove financial data.")
    op.drop_table("prescription_prices", schema="fulfilment")
    op.drop_column("orders", "pricing_mode", schema="fulfilment")
