"""Enforce inventory_transactions append-only at the database level.

The ledger is the billing source of truth. models/inventory.py documents it as
"NEVER updated, only appended", but until now that was convention — the app
role could rewrite billing history silently. This trigger makes UPDATE
impossible and DELETE possible only for the sanctioned admin wipe flows
(maintenance tenant data clear/reset), which set a transaction-local GUC
before deleting:

    SELECT set_config('app.allow_ledger_admin_delete', 'true', true)

PostgreSQL only — SQLite dev/test databases skip it (same as RLS).

Revision ID: 018
Revises: 017
Create Date: 2026-08-06
"""

import sqlalchemy as sa

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


TRIGGER_FN = """
CREATE OR REPLACE FUNCTION inventory_transactions_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('app.allow_ledger_admin_delete', true) = 'true' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'inventory_transactions is an append-only ledger (op=%). Admin wipe flows '
        'must set app.allow_ledger_admin_delete for their transaction.', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(TRIGGER_FN))
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_inventory_transactions_append_only "
            "ON inventory_transactions"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_inventory_transactions_append_only "
            "BEFORE UPDATE OR DELETE ON inventory_transactions "
            "FOR EACH ROW EXECUTE FUNCTION inventory_transactions_append_only()"
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_inventory_transactions_append_only "
            "ON inventory_transactions"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS inventory_transactions_append_only()"))
