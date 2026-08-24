"""Index tuning: billing/ledger indexes, task queue indexes, drop redundancies.

Adds:
- inventory_transactions billing/reporting indexes — billing_service scans the
  ledger by (tenant, client, transaction_type, performed_at range) four times
  per client per period with no index today.
- tasks AGV warehouse-queue index and per-worker workload index.
- inbound_orders (tenant, warehouse, created_at) — outbound has had this since
  migration 007; inbound was missed.

Drops 15 single-column tenant_id indexes that are fully covered by the leading
column of a tenant-first composite index on the same table (pure write
amplification, no read benefit).

Revision ID: 017
Revises: 016
Create Date: 2026-08-06
"""

from sqlalchemy import inspect

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


NEW_INDEXES = [
    (
        "ix_invtx_tenant_client_type_performed",
        "inventory_transactions",
        ["tenant_id", "client_id", "transaction_type", "performed_at"],
    ),
    ("ix_invtx_tenant_performed", "inventory_transactions", ["tenant_id", "performed_at"]),
    (
        "ix_tasks_tenant_warehouse_queue",
        "tasks",
        ["tenant_id", "warehouse_id", "status", "assigned_type", "priority", "created_at"],
    ),
    ("ix_tasks_tenant_assigned_status", "tasks", ["tenant_id", "assigned_to", "status"]),
    (
        "ix_inbound_orders_tenant_warehouse_created",
        "inbound_orders",
        ["tenant_id", "warehouse_id", "created_at"],
    ),
]

# Single-column tenant_id indexes covered by tenant-leading composites.
REDUNDANT_TENANT_INDEXES = [
    ("inventory", "ix_inventory_tenant_id"),
    ("inventory_transactions", "ix_inventory_transactions_tenant_id"),
    ("inbound_orders", "ix_inbound_orders_tenant_id"),
    ("inbound_order_lines", "ix_inbound_order_lines_tenant_id"),
    ("inbound_packages", "ix_inbound_packages_tenant_id"),
    ("receiving_labels", "ix_receiving_labels_tenant_id"),
    ("handling_units", "ix_handling_units_tenant_id"),
    ("receiving_observed_codes", "ix_receiving_observed_codes_tenant_id"),
    ("outbound_orders", "ix_outbound_orders_tenant_id"),
    ("outbound_order_lines", "ix_outbound_order_lines_tenant_id"),
    ("tasks", "ix_tasks_tenant_id"),
    ("invoices", "ix_invoices_tenant_id"),
    ("agent_evidence", "ix_agent_evidence_tenant_id"),
    ("idempotency_records", "ix_idempotency_records_tenant_id"),
    ("wcs_task_bindings", "ix_wcs_task_bindings_tenant_id"),
]


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    for name, table, columns in NEW_INDEXES:
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)

    for table, name in REDUNDANT_TENANT_INDEXES:
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)


def downgrade() -> None:
    for table, name in REDUNDANT_TENANT_INDEXES:
        op.create_index(name, table, ["tenant_id"])
    for name, table, _columns in reversed(NEW_INDEXES):
        op.drop_index(name, table_name=table)
