"""Enable RLS for all current tenant-scoped tables.

Revision ID: 003
Revises: 002
Create Date: 2026-04-26
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


TENANT_TABLES = [
    "billing_line_items",
    "billing_periods",
    "clients",
    "handling_units",
    "inbound_order_lines",
    "inbound_orders",
    "inbound_packages",
    "inventory",
    "inventory_transactions",
    "invoices",
    "kit_components",
    "kits",
    "locations",
    "outbound_order_lines",
    "outbound_orders",
    "pick_allocations",
    "putaway_allocations",
    "rate_cards",
    "receiving_labels",
    "receiving_observed_codes",
    "return_order_lines",
    "return_orders",
    "skus",
    "subscriptions",
    "tasks",
    "users",
    "warehouses",
    "zones",
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id::text = current_setting('app.current_tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
            """
        )
        op.execute(
            f"""
            CREATE POLICY admin_bypass ON {table}
                USING (current_setting('app.is_platform_admin', true) = 'true')
            """
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
