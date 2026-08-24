"""Add tenant-scoped idempotency records.

Revision ID: 011
Revises: 010
Create Date: 2026-05-05
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "idempotency_records" not in inspector.get_table_names():
        op.create_table(
            "idempotency_records",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("operation", sa.String(length=160), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("response_status_code", sa.Integer(), nullable=True),
            sa.Column(
                "response_json",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_idempotency_tenant_key"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_idempotency_records_tenant_id "
        "ON idempotency_records (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_idempotency_tenant_operation "
        "ON idempotency_records (tenant_id, operation)"
    )

    op.execute("ALTER TABLE idempotency_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE idempotency_records FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON idempotency_records")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON idempotency_records")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON idempotency_records
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY admin_bypass ON idempotency_records
            USING (current_setting('app.is_platform_admin', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON idempotency_records")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON idempotency_records")
    op.execute("ALTER TABLE idempotency_records DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_idempotency_tenant_operation")
    op.execute("DROP INDEX IF EXISTS ix_idempotency_records_tenant_id")
    op.drop_table("idempotency_records")
