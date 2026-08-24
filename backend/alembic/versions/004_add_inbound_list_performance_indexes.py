"""Add inbound list performance indexes.

Revision ID: 004
Revises: 003
Create Date: 2026-04-27
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


INDEX_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_orders_tenant_created
    ON inbound_orders (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_orders_tenant_status_created
    ON inbound_orders (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_order_lines_tenant_order
    ON inbound_order_lines (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_packages_tenant_order_status
    ON inbound_packages (tenant_id, order_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_receiving_labels_tenant_order_status
    ON receiving_labels (tenant_id, order_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_receiving_observed_codes_tenant_order
    ON receiving_observed_codes (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_handling_units_tenant_order
    ON handling_units (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_transactions_tenant_reference
    ON inventory_transactions (tenant_id, reference_type, reference_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_reference
    ON tasks (tenant_id, reference_type, reference_id)
    """,
]

INDEX_NAMES = [
    "ix_tasks_tenant_reference",
    "ix_inventory_transactions_tenant_reference",
    "ix_handling_units_tenant_order",
    "ix_receiving_observed_codes_tenant_order",
    "ix_receiving_labels_tenant_order_status",
    "ix_inbound_packages_tenant_order_status",
    "ix_inbound_order_lines_tenant_order",
    "ix_inbound_orders_tenant_status_created",
    "ix_inbound_orders_tenant_created",
]


def upgrade() -> None:
    for statement in INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for index_name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
