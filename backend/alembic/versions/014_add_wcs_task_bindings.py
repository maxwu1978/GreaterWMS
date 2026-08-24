"""Add WCS task bindings.

Revision ID: 014
Revises: 013
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "wcs_task_bindings" not in inspector.get_table_names():
        op.create_table(
            "wcs_task_bindings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("warehouse_id", sa.String(length=36), nullable=False),
            sa.Column("wcs_task_id", sa.String(length=80), nullable=True),
            sa.Column("wcs_step_id", sa.String(length=80), nullable=True),
            sa.Column("task_psn", sa.String(length=120), nullable=True),
            sa.Column("agv_unit_id", sa.String(length=80), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("start_pos", sa.String(length=120), nullable=False),
            sa.Column("end_pos", sa.String(length=120), nullable=False),
            sa.Column("task_type", sa.String(length=80), nullable=True),
            sa.Column("last_step_status", sa.Integer(), nullable=True),
            sa.Column("last_step_status_name", sa.String(length=80), nullable=True),
            sa.Column("last_callback_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column(
                "request_payload",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "response_payload",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "last_callback_payload",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "task_id", name="uq_wcs_binding_tenant_task"),
            sa.UniqueConstraint(
                "tenant_id", "wcs_task_id", name="uq_wcs_binding_tenant_wcs_task"
            ),
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_wcs_task_bindings_tenant_id ON wcs_task_bindings (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wcs_bindings_tenant_status "
        "ON wcs_task_bindings (tenant_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wcs_bindings_tenant_psn "
        "ON wcs_task_bindings (tenant_id, task_psn)"
    )

    op.execute("ALTER TABLE wcs_task_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE wcs_task_bindings FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON wcs_task_bindings")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON wcs_task_bindings")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON wcs_task_bindings
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY admin_bypass ON wcs_task_bindings
            USING (current_setting('app.is_platform_admin', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON wcs_task_bindings")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON wcs_task_bindings")
    op.execute("ALTER TABLE wcs_task_bindings DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_wcs_bindings_tenant_psn")
    op.execute("DROP INDEX IF EXISTS ix_wcs_bindings_tenant_status")
    op.execute("DROP INDEX IF EXISTS ix_wcs_task_bindings_tenant_id")
    op.drop_table("wcs_task_bindings")
