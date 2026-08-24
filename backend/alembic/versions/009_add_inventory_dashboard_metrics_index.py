"""Add inventory dashboard metrics covering index.

Revision ID: 009
Revises: 008
Create Date: 2026-05-01
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_live_metrics
        ON inventory (tenant_id, warehouse_id, sku_id, location_id, quantity_on_hand)
        WHERE quantity_on_hand > 0
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inventory_tenant_warehouse_live_metrics")
