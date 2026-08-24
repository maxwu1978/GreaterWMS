"""Add pick allocation details.

Revision ID: 005
Revises: 004
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "pick_allocations" not in inspector.get_table_names():
        op.create_table(
            "pick_allocations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("order_id", sa.String(length=36), nullable=False),
            sa.Column("order_line_id", sa.String(length=36), nullable=False),
            sa.Column("warehouse_id", sa.String(length=36), nullable=False),
            sa.Column("sku_id", sa.String(length=36), nullable=False),
            sa.Column("location_id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=True),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("quantity_picked", sa.Integer(), server_default="0", nullable=False),
            sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["outbound_orders.id"]),
            sa.ForeignKeyConstraint(["order_line_id"], ["outbound_order_lines.id"]),
            sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pick_allocations_tenant_id "
        "ON pick_allocations (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pick_allocations_order_id "
        "ON pick_allocations (order_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pick_allocations_order_line_id "
        "ON pick_allocations (order_line_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pick_allocations_task_id "
        "ON pick_allocations (task_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pick_allocations_task_id")
    op.execute("DROP INDEX IF EXISTS ix_pick_allocations_order_line_id")
    op.execute("DROP INDEX IF EXISTS ix_pick_allocations_order_id")
    op.execute("DROP INDEX IF EXISTS ix_pick_allocations_tenant_id")
    op.drop_table("pick_allocations")
