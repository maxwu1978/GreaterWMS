"""Enable Row-Level Security on all tenant-scoped tables.

Revision ID: 001
Revises: None
Create Date: 2026-04-05
"""

from alembic import op
from app.models import Base

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# All tables that have tenant_id and need RLS
TENANT_TABLES = [
    "users",
    "clients",
    "warehouses",
    "zones",
    "locations",
    "skus",
    "inventory",
    "inventory_transactions",
    "inbound_orders",
    "inbound_order_lines",
    "outbound_orders",
    "outbound_order_lines",
    "tasks",
    "rate_cards",
    "billing_periods",
    "billing_line_items",
    "invoices",
]


def upgrade() -> None:
    # Historical migrations originally assumed application tables already existed
    # from the startup bootstrap path. Keep fresh database upgrades self-contained
    # by creating the current model tables before the RLS-only revisions run.
    Base.metadata.create_all(bind=op.get_bind())

    for table in TENANT_TABLES:
        # Enable RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table}")

        # Tenant isolation policy: rows visible only when tenant_id matches session var
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id::text = current_setting('app.current_tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """)

        # Platform admin bypass: when app.is_platform_admin = 'true'
        op.execute(f"""
            CREATE POLICY admin_bypass ON {table}
                USING (current_setting('app.is_platform_admin', true) = 'true')
        """)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"DROP POLICY IF EXISTS admin_bypass ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
