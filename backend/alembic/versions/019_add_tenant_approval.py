"""Add registration approval fields to tenants.

New workspaces can be gated behind platform-admin approval
(REGISTRATION_APPROVAL_REQUIRED). Existing tenants are backfilled as approved.

Revision ID: 019
Revises: 018
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("tenants")}
    if "approval_status" not in existing:
        op.add_column(
            "tenants",
            sa.Column(
                "approval_status",
                sa.String(20),
                nullable=False,
                server_default="approved",
            ),
        )
    if "approved_at" not in existing:
        op.add_column("tenants", sa.Column("approved_at", sa.DateTime(timezone=True)))
    if "approved_by" not in existing:
        op.add_column("tenants", sa.Column("approved_by", sa.String(36)))


def downgrade() -> None:
    op.drop_column("tenants", "approved_by")
    op.drop_column("tenants", "approved_at")
    op.drop_column("tenants", "approval_status")
