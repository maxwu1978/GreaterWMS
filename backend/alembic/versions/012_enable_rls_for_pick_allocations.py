"""Enable RLS for pick allocations.

Revision ID: 012
Revises: 011
Create Date: 2026-05-05
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE pick_allocations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pick_allocations FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON pick_allocations")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON pick_allocations")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON pick_allocations
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY admin_bypass ON pick_allocations
            USING (current_setting('app.is_platform_admin', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON pick_allocations")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON pick_allocations")
    op.execute("ALTER TABLE pick_allocations DISABLE ROW LEVEL SECURITY")
