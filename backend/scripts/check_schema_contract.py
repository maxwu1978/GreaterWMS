#!/usr/bin/env python3
"""Read-only schema contract check for production and release gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

REPO_BACKEND = Path(__file__).resolve().parents[1]

REQUIRED_COLUMNS: dict[str, set[str]] = {
    "alembic_version": {"version_num"},
    "agent_evidence": {
        "id",
        "tenant_id",
        "action",
        "risk",
        "required_permission",
        "entity_type",
        "entity_id",
        "status",
        "payload_hash",
        "confirmation_token_hash",
        "planned_endpoint",
        "state_before",
        "state_after",
        "planned_request",
        "confirmation_payload",
        "result",
        "expires_at",
    },
    "idempotency_records": {
        "id",
        "tenant_id",
        "idempotency_key",
        "operation",
        "request_hash",
        "status",
        "response_status_code",
        "response_json",
    },
    "locations": {
        "dimensions",
        "layout_metadata",
        "drawing_source",
        "wcs_point_metadata",
    },
    "outbound_orders": {
        "pick_readiness_rank",
        "shipping_readiness_rank",
    },
    "pick_allocations": {
        "id",
        "tenant_id",
        "order_id",
        "order_line_id",
        "warehouse_id",
        "sku_id",
        "location_id",
        "task_id",
        "quantity",
        "quantity_picked",
    },
    "tasks": {"handling_unit_id", "execution_mode"},
    "wcs_task_bindings": {
        "id",
        "tenant_id",
        "task_id",
        "warehouse_id",
        "wcs_task_id",
        "wcs_step_id",
        "task_psn",
        "status",
        "start_pos",
        "end_pos",
        "request_payload",
        "response_payload",
        "last_callback_payload",
    },
    "zones": {
        "zone_type",
        "coordinate_x",
        "coordinate_y",
        "coordinate_z",
        "dimensions",
        "layout_metadata",
        "drawing_source",
    },
}

REQUIRED_INDEXES = {
    "ix_agent_evidence_tenant_action_status",
    "ix_agent_evidence_tenant_id",
    "ix_agent_evidence_tenant_payload",
    "ix_handling_units_tenant_order",
    "ix_idempotency_tenant_operation",
    "ix_idempotency_records_tenant_id",
    "ix_inbound_order_lines_tenant_order",
    "ix_inbound_orders_tenant_created",
    "ix_inbound_orders_tenant_status_created",
    "ix_inbound_packages_tenant_order_status",
    "ix_inventory_tenant_live_metrics",
    "ix_inventory_tenant_live_order",
    "ix_inventory_tenant_warehouse_live_metrics",
    "ix_inventory_tenant_warehouse_location_sku",
    "ix_inventory_tenant_warehouse_sku",
    "ix_inventory_transactions_tenant_reference",
    "ix_invoices_tenant_client_created",
    "ix_invoices_tenant_created",
    "ix_invoices_tenant_status_created",
    "ix_outbound_order_lines_tenant_order",
    "ix_outbound_order_lines_tenant_sku_order",
    "ix_outbound_orders_tenant_created",
    "ix_outbound_orders_tenant_pick_readiness_created_desc",
    "ix_outbound_orders_tenant_shipping_readiness_created_desc",
    "ix_outbound_orders_tenant_status_created",
    "ix_outbound_orders_tenant_warehouse_created",
    "ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc",
    "ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc",
    "ix_outbound_orders_tenant_warehouse_status_created",
    "ix_pick_allocations_order_id",
    "ix_pick_allocations_order_line_id",
    "ix_pick_allocations_task_id",
    "ix_pick_allocations_tenant_id",
    "ix_receiving_labels_tenant_order_status",
    "ix_receiving_observed_codes_tenant_order",
    "ix_tasks_tenant_queue",
    "ix_tasks_tenant_reference",
    "ix_tasks_tenant_status_type_priority_created",
    "ix_wcs_bindings_tenant_psn",
    "ix_wcs_bindings_tenant_status",
    "ix_wcs_task_bindings_tenant_id",
    "uq_agent_evidence_token",
    "uq_idempotency_tenant_key",
    "uq_tasks_inbound_putaway_handling_unit",
    "uq_wcs_binding_tenant_task",
    "uq_wcs_binding_tenant_wcs_task",
}

REQUIRED_INDEX_ALIASES = {
    # PostgreSQL truncates identifiers to 63 bytes. The Alembic statement uses
    # the full descriptive name, while pg_indexes reports the truncated name.
    "ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc": {
        "ix_outbound_orders_tenant_warehouse_shipping_readiness_created_",
    },
}

REQUIRED_POSTGRES_RLS_TABLES = {
    "agent_evidence",
    "idempotency_records",
    "locations",
    "pick_allocations",
    "tasks",
    "wcs_task_bindings",
    "zones",
}


def _read_dotenv_database_url() -> str | None:
    env_path = REPO_BACKEND / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "DATABASE_URL":
            return value.strip().strip("'\"")
    return None


def _database_url(args: argparse.Namespace) -> str:
    database_url = args.database_url or os.environ.get("DATABASE_URL") or _read_dotenv_database_url()
    if not database_url:
        raise SystemExit("DATABASE_URL is required, or pass --database-url")
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _local_alembic_heads() -> list[str]:
    versions_dir = REPO_BACKEND / "alembic" / "versions"
    revisions: set[str] = set()
    down_revisions: set[str] = set()
    revision_pattern = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    down_pattern = re.compile(r"^down_revision\s*=\s*(.+)$", re.MULTILINE)

    for path in versions_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision_match = revision_pattern.search(source)
        if revision_match:
            revisions.add(revision_match.group(1))
        down_match = down_pattern.search(source)
        if not down_match:
            continue
        down_value = down_match.group(1).strip()
        if down_value == "None":
            continue
        down_revisions.update(re.findall(r"['\"]([^'\"]+)['\"]", down_value))
    return sorted(revisions - down_revisions)


async def _postgres_snapshot(conn) -> dict[str, Any]:
    columns_result = await conn.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            """
        )
    )
    columns: dict[str, set[str]] = {}
    for table_name, column_name in columns_result:
        columns.setdefault(table_name, set()).add(column_name)

    index_result = await conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    )
    indexes = {row[0] for row in index_result}

    rls_table_list = ", ".join(f"'{table}'" for table in sorted(REQUIRED_POSTGRES_RLS_TABLES))
    rls_result = await conn.execute(
        text(
            f"""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relname IN ({rls_table_list})
            """
        )
    )
    rls = {
        row[0]: {"enabled": bool(row[1]), "forced": bool(row[2])}
        for row in rls_result
    }

    revisions: list[str] = []
    if "alembic_version" in columns:
        revision_result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        revisions = [row[0] for row in revision_result]
    return {"columns": columns, "indexes": indexes, "rls": rls, "revisions": revisions}


async def _sqlite_snapshot(conn) -> dict[str, Any]:
    tables_result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table'")
    )
    tables = [row[0] for row in tables_result]
    columns: dict[str, set[str]] = {}
    indexes: set[str] = set()
    for table_name in tables:
        column_result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns[table_name] = {row[1] for row in column_result}
        index_result = await conn.execute(text(f"PRAGMA index_list({table_name})"))
        indexes.update(row[1] for row in index_result)

    revisions: list[str] = []
    if "alembic_version" in columns:
        revision_result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        revisions = [row[0] for row in revision_result]
    return {"columns": columns, "indexes": indexes, "rls": {}, "revisions": revisions}


async def run_check(args: argparse.Namespace) -> dict[str, Any]:
    database_url = _database_url(args)
    url = make_url(database_url)
    dialect = url.get_backend_name()
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            snapshot = (
                await _postgres_snapshot(conn)
                if dialect == "postgresql"
                else await _sqlite_snapshot(conn)
            )
    finally:
        await engine.dispose()

    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    for table_name, required_columns in sorted(REQUIRED_COLUMNS.items()):
        actual_columns = snapshot["columns"].get(table_name)
        if actual_columns is None:
            missing_tables.append(table_name)
            continue
        missing = sorted(required_columns - actual_columns)
        if missing:
            missing_columns[table_name] = missing

    missing_indexes = sorted(
        required_index
        for required_index in REQUIRED_INDEXES
        if not ({required_index} | REQUIRED_INDEX_ALIASES.get(required_index, set()))
        & snapshot["indexes"]
    )
    rls_failures = {
        table_name: state
        for table_name, state in sorted(snapshot["rls"].items())
        if not state.get("enabled") or not state.get("forced")
    }
    for table_name in REQUIRED_POSTGRES_RLS_TABLES - snapshot["rls"].keys():
        if dialect == "postgresql":
            rls_failures[table_name] = {"enabled": False, "forced": False}

    heads = _local_alembic_heads()
    revisions = sorted(snapshot["revisions"])
    warnings: list[str] = []
    if heads and revisions != heads:
        warnings.append(
            f"alembic_version drift: database={revisions or ['<missing>']} local_heads={heads}"
        )

    errors: list[str] = []
    if missing_tables:
        errors.append(f"missing tables: {', '.join(missing_tables)}")
    if missing_columns:
        errors.append(f"missing columns: {json.dumps(missing_columns, sort_keys=True)}")
    if missing_indexes:
        errors.append(f"missing indexes: {', '.join(missing_indexes)}")
    if rls_failures:
        errors.append(f"RLS not enabled/forced: {json.dumps(rls_failures, sort_keys=True)}")
    if args.strict_alembic and warnings:
        errors.extend(warnings)

    return {
        "ok": not errors,
        "dialect": dialect,
        "local_alembic_heads": heads,
        "database_alembic_revisions": revisions,
        "required_tables": sorted(REQUIRED_COLUMNS),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "missing_indexes": missing_indexes,
        "rls_failures": rls_failures,
        "warnings": warnings,
        "errors": errors,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="SQLAlchemy async database URL. Defaults to DATABASE_URL.")
    parser.add_argument(
        "--strict-alembic",
        action="store_true",
        help="Fail when alembic_version does not exactly match local heads.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    result = asyncio.run(run_check(parse_args(argv)))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
