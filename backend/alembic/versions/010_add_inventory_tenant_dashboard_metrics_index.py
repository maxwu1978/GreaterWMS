"""Add tenant-wide inventory dashboard metrics index.

Revision ID: 010
Revises: 009
Create Date: 2026-05-01
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_inventory_tenant_live_metrics
        ON inventory (tenant_id, sku_id, location_id, warehouse_id, quantity_on_hand)
        WHERE quantity_on_hand > 0
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inventory_tenant_live_metrics")
