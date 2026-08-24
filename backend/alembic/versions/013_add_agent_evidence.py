"""Add agent operation evidence.

Revision ID: 013
Revises: 012
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_evidence" not in inspector.get_table_names():
        op.create_table(
            "agent_evidence",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("action", sa.String(length=120), nullable=False),
            sa.Column("risk", sa.String(length=20), nullable=False),
            sa.Column("required_permission", sa.String(length=120), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=False),
            sa.Column("actor_user_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("confirmation_token_hash", sa.String(length=64), nullable=False),
            sa.Column("planned_endpoint", sa.String(length=260), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column(
                "state_before",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "state_after",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "planned_request",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "confirmation_payload",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column(
                "result",
                sa.JSON().with_variant(postgresql.JSONB, "postgresql"),
                nullable=True,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "confirmation_token_hash", name="uq_agent_evidence_token"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_id ON agent_evidence (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_action_status "
        "ON agent_evidence (tenant_id, action, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_payload "
        "ON agent_evidence (tenant_id, payload_hash)"
    )

    op.execute("ALTER TABLE agent_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_evidence FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON agent_evidence")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON agent_evidence")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON agent_evidence
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
        """
    )
    op.execute(
        """
        CREATE POLICY admin_bypass ON agent_evidence
            USING (current_setting('app.is_platform_admin', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON agent_evidence")
    op.execute("DROP POLICY IF EXISTS admin_bypass ON agent_evidence")
    op.execute("ALTER TABLE agent_evidence DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_agent_evidence_tenant_payload")
    op.execute("DROP INDEX IF EXISTS ix_agent_evidence_tenant_action_status")
    op.execute("DROP INDEX IF EXISTS ix_agent_evidence_tenant_id")
    op.drop_table("agent_evidence")
