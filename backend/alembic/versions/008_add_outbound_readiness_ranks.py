"""Add persisted outbound readiness ranks.

Revision ID: 008
Revises: 007
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


INDEX_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_pick_readiness_created_desc
    ON outbound_orders (tenant_id, pick_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc
    ON outbound_orders (tenant_id, warehouse_id, pick_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_shipping_readiness_created_desc
    ON outbound_orders (tenant_id, shipping_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc
    ON outbound_orders (tenant_id, warehouse_id, shipping_readiness_rank, created_at DESC)
    """,
]

INDEX_NAMES = [
    "ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc",
    "ix_outbound_orders_tenant_shipping_readiness_created_desc",
    "ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc",
    "ix_outbound_orders_tenant_pick_readiness_created_desc",
]


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("outbound_orders", "pick_readiness_rank"):
        op.add_column(
            "outbound_orders",
            sa.Column("pick_readiness_rank", sa.Integer(), nullable=False, server_default="90"),
        )
    if not _has_column("outbound_orders", "shipping_readiness_rank"):
        op.add_column(
            "outbound_orders",
            sa.Column(
                "shipping_readiness_rank",
                sa.Integer(),
                nullable=False,
                server_default="90",
            ),
        )
    op.execute(
        """
        UPDATE outbound_orders
        SET pick_readiness_rank = CASE
            WHEN status = 'pending' THEN 20
            WHEN status = 'allocated' THEN 30
            WHEN status = 'picking' THEN 40
            WHEN status = 'picked' THEN 50
            WHEN status = 'packing' THEN 50
            WHEN status = 'packed' THEN 60
            WHEN status = 'shipped' THEN 70
            ELSE 90
        END,
        shipping_readiness_rank = CASE
            WHEN status = 'packed'
             AND COALESCE(carrier, '') <> ''
             AND COALESCE(tracking_number, '') <> '' THEN 10
            WHEN status = 'packed' THEN 20
            WHEN status = 'packing' THEN 30
            WHEN status = 'picked' THEN 40
            WHEN status = 'shipped' THEN 70
            ELSE 90
        END
        WHERE pick_readiness_rank = 90
          AND shipping_readiness_rank = 90
        """
    )
    for statement in INDEX_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for index_name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    if _has_column("outbound_orders", "shipping_readiness_rank"):
        op.drop_column("outbound_orders", "shipping_readiness_rank")
    if _has_column("outbound_orders", "pick_readiness_rank"):
        op.drop_column("outbound_orders", "pick_readiness_rank")
