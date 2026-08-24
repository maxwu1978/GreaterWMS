"""Add outbound, inventory, and billing list indexes.

Revision ID: 007
Revises: 006
Create Date: 2026-05-01
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


INDEX_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_created
    ON outbound_orders (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_created
    ON outbound_orders (tenant_id, warehouse_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_status_created
    ON outbound_orders (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_status_created
    ON outbound_orders (tenant_id, warehouse_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_order_lines_tenant_order
    ON outbound_order_lines (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_order_lines_tenant_sku_order
    ON outbound_order_lines (tenant_id, sku_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_status_type_priority_created
    ON tasks (tenant_id, status, task_type, priority, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_sku
    ON inventory (tenant_id, warehouse_id, sku_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_live_order
    ON inventory (tenant_id, warehouse_id, sku_id, location_id, lot_number, id)
    WHERE quantity_on_hand > 0
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_created
    ON invoices (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_status_created
    ON invoices (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_client_created
    ON invoices (tenant_id, client_id, created_at)
    """,
]

INDEX_NAMES = [
    "ix_invoices_tenant_client_created",
    "ix_invoices_tenant_status_created",
    "ix_invoices_tenant_created",
    "ix_inventory_tenant_live_order",
    "ix_inventory_tenant_warehouse_sku",
    "ix_tasks_tenant_status_type_priority_created",
    "ix_outbound_order_lines_tenant_sku_order",
    "ix_outbound_order_lines_tenant_order",
    "ix_outbound_orders_tenant_warehouse_status_created",
    "ix_outbound_orders_tenant_status_created",
    "ix_outbound_orders_tenant_warehouse_created",
    "ix_outbound_orders_tenant_created",
]


def upgrade() -> None:
    for statement in INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for index_name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
