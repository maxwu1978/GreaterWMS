"""Add inbound putaway task uniqueness guard.

Revision ID: 002
Revises: 001
Create Date: 2026-04-26
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_inbound_putaway_handling_unit
        ON tasks (tenant_id, task_type, reference_type, reference_id, handling_unit_id)
        WHERE task_type = 'putaway'
          AND reference_type = 'inbound_order'
          AND reference_id IS NOT NULL
          AND handling_unit_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tasks_inbound_putaway_handling_unit")
