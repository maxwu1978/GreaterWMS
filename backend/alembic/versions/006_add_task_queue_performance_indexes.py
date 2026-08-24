"""Add task queue performance indexes.

Revision ID: 006
Revises: 005
Create Date: 2026-05-01
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


INDEX_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_queue
    ON tasks (tenant_id, status, task_type, assigned_type, warehouse_id, priority, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_location_sku
    ON inventory (tenant_id, warehouse_id, location_id, sku_id)
    """,
]


def upgrade() -> None:
    for statement in INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inventory_tenant_warehouse_location_sku")
    op.execute("DROP INDEX IF EXISTS ix_tasks_tenant_queue")
