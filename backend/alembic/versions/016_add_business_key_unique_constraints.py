"""Add unique constraints on business keys + the inventory natural key.

Until now every business key (order numbers, client/SKU/warehouse codes,
location barcodes, invoice/RMA numbers, label/unit codes) was guarded only by
check-then-insert in application code — a TOCTOU race under concurrency.
This migration makes the database the source of truth.

Each constraint is preceded by a duplicate probe: if existing rows violate the
key, the migration aborts with the offending values so the operator can resolve
them deliberately (auto-deduping order numbers would be far more dangerous).

Revision ID: 016
Revises: 015
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


# (table, constraint name, columns)
UNIQUE_CONSTRAINTS = [
    ("clients", "uq_clients_tenant_code", ["tenant_id", "code"]),
    ("skus", "uq_skus_tenant_client_code", ["tenant_id", "client_id", "sku_code"]),
    ("warehouses", "uq_warehouses_tenant_code", ["tenant_id", "code"]),
    ("zones", "uq_zones_tenant_wh_code", ["tenant_id", "warehouse_id", "code"]),
    # Scan lookups resolve barcodes tenant-wide (websocket/scanner.py), so the
    # key is (tenant, barcode) — not per-warehouse.
    ("locations", "uq_locations_tenant_barcode", ["tenant_id", "barcode"]),
    ("inbound_orders", "uq_inbound_orders_tenant_order_number", ["tenant_id", "order_number"]),
    ("outbound_orders", "uq_outbound_orders_tenant_order_number", ["tenant_id", "order_number"]),
    ("invoices", "uq_invoices_tenant_number", ["tenant_id", "invoice_number"]),
    ("return_orders", "uq_return_orders_tenant_rma", ["tenant_id", "rma_number"]),
    ("receiving_labels", "uq_receiving_labels_tenant_label_code", ["tenant_id", "label_code"]),
    ("handling_units", "uq_handling_units_tenant_unit_code", ["tenant_id", "unit_code"]),
    ("kits", "uq_kits_tenant_sku", ["tenant_id", "sku_id"]),
]

INVENTORY_KEY_EXPRS = [
    "tenant_id",
    "location_id",
    "sku_id",
    "coalesce(lpn, '')",
    "coalesce(lot_number, '')",
    "coalesce(expiry_date, '1970-01-01')",
]


def _assert_no_duplicates(conn, table: str, exprs: list[str]) -> None:
    cols = ", ".join(exprs)
    rows = conn.execute(
        sa.text(
            f"SELECT {cols}, count(*) AS n FROM {table} "
            f"GROUP BY {cols} HAVING count(*) > 1 LIMIT 5"
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            f"Cannot add unique constraint on {table}({cols}): duplicate rows exist. "
            f"Resolve these first (sample): {[tuple(r) for r in rows]}"
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Migration 001 bootstraps fresh databases via Base.metadata.create_all, so
    # on a new database these constraints already exist — guard for idempotency
    # (same pattern as migration 015). On pre-existing databases this migration
    # does the real work, with duplicate pre-checks.
    for table, name, columns in UNIQUE_CONSTRAINTS:
        existing = {c["name"] for c in inspector.get_unique_constraints(table)}
        if name in existing:
            continue
        _assert_no_duplicates(conn, table, columns)
        op.create_unique_constraint(name, table, columns)

    # Inventory natural key: "one row per stock position" (see models/inventory.py).
    # Nullable dims are coalesced so NULLs collide instead of being always-distinct.
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("inventory")}
    if "uq_inventory_stock_position" in existing_indexes:
        return
    _assert_no_duplicates(conn, "inventory", INVENTORY_KEY_EXPRS)
    op.create_index(
        "uq_inventory_stock_position",
        "inventory",
        [
            sa.text("tenant_id"),
            sa.text("location_id"),
            sa.text("sku_id"),
            sa.text("coalesce(lpn, '')"),
            sa.text("coalesce(lot_number, '')"),
            sa.text("coalesce(expiry_date, '1970-01-01')"),
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_inventory_stock_position", table_name="inventory")
    for table, name, _columns in reversed(UNIQUE_CONSTRAINTS):
        op.drop_constraint(name, table, type_="unique")
