"""Print representative query plans for WMS operational hot paths.

Usage:
    python scripts/check_query_plans.py
    python scripts/check_query_plans.py --tenant-id <tenant> --analyze

The script uses the configured DATABASE_URL. Default EXPLAIN mode is read-only;
--analyze executes the statements and should be used only against staging or a
safe production maintenance window.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine


async def _scalar(sql: str, params: dict | None = None) -> str | None:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params or {})


async def _choose_context(tenant_id: str | None) -> dict[str, str | None]:
    tenant = tenant_id or await _scalar("SELECT id FROM tenants ORDER BY created_at LIMIT 1")
    warehouse = None
    sku = None
    if tenant:
        warehouse = await _scalar(
            """
            SELECT warehouse_id
            FROM inventory
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"tenant_id": tenant},
        )
        sku = await _scalar(
            """
            SELECT sku_id
            FROM inventory
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
            LIMIT 1
            """,
            {"tenant_id": tenant},
        )
    return {"tenant_id": tenant, "warehouse_id": warehouse, "sku_id": sku}


def _explain_prefix(dialect: str, analyze: bool) -> str:
    if dialect == "sqlite":
        if analyze:
            raise SystemExit("--analyze is only supported for PostgreSQL query plans.")
        return "EXPLAIN QUERY PLAN"
    return "EXPLAIN (ANALYZE, BUFFERS)" if analyze else "EXPLAIN"


def _inventory_query(context: dict[str, str | None]) -> tuple[str, dict]:
    params = {"tenant_id": context["tenant_id"]}
    predicates = ["tenant_id = :tenant_id", "quantity_on_hand > 0"]
    if context["warehouse_id"]:
        predicates.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = context["warehouse_id"]
    if context["sku_id"]:
        predicates.append("sku_id = :sku_id")
        params["sku_id"] = context["sku_id"]
    return (
        f"""
        SELECT id
        FROM inventory
        WHERE {" AND ".join(predicates)}
        LIMIT 101
        """,
        params,
    )


def _queries(context: dict[str, str | None]) -> Sequence[tuple[str, str, dict]]:
    tenant_id = context["tenant_id"]
    inventory_sql, inventory_params = _inventory_query(context)
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    last_7d_start = today_start - timedelta(days=7)
    dashboard_params = {
        "tenant_id": tenant_id,
        "today_start": today_start,
        "last_7d_start": last_7d_start,
    }
    warehouse_filter = ""
    if context["warehouse_id"]:
        warehouse_filter = "AND warehouse_id = :warehouse_id"
        dashboard_params["warehouse_id"] = context["warehouse_id"]
    return [
        (
            "task_queue",
            """
            SELECT id
            FROM tasks
            WHERE tenant_id = :tenant_id
              AND status = 'pending'
              AND task_type = 'putaway'
            ORDER BY priority ASC, created_at ASC
            LIMIT 100
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "inbound_order_list",
            """
            SELECT id
            FROM inbound_orders
            WHERE tenant_id = :tenant_id
              AND status IN ('expected', 'arrived', 'receiving', 'putaway')
            ORDER BY created_at DESC
            LIMIT 101
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "outbound_order_default_sort",
            """
            SELECT id
            FROM outbound_orders
            WHERE tenant_id = :tenant_id
              AND status IN ('pending', 'allocated', 'picking')
            ORDER BY created_at DESC
            LIMIT 101
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "outbound_pick_readiness_sort",
            """
            SELECT id
            FROM outbound_orders
            WHERE tenant_id = :tenant_id
              AND status IN ('pending', 'allocated', 'picking')
            ORDER BY pick_readiness_rank ASC, created_at DESC
            LIMIT 101
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "outbound_shipping_readiness_sort",
            """
            SELECT id
            FROM outbound_orders
            WHERE tenant_id = :tenant_id
              AND status IN ('picked', 'packing', 'packed', 'shipped')
            ORDER BY shipping_readiness_rank ASC, created_at DESC
            LIMIT 101
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "inventory_by_warehouse_sku_window",
            inventory_sql,
            inventory_params,
        ),
        (
            "inventory_endpoint_stable_order",
            """
            SELECT id
            FROM inventory
            WHERE tenant_id = :tenant_id
              AND quantity_on_hand > 0
            ORDER BY
              warehouse_id ASC,
              sku_id ASC,
              location_id ASC,
              lot_number ASC,
              id ASC
            LIMIT 101
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "billing_invoice_followup",
            """
            SELECT invoices.id
            FROM invoices
            JOIN clients ON clients.id = invoices.client_id
            WHERE invoices.tenant_id = :tenant_id
            ORDER BY invoices.created_at DESC
            LIMIT 200
            """,
            {"tenant_id": tenant_id},
        ),
        (
            "dashboard_outbound_metrics_tenant",
            """
            SELECT
              SUM(CASE
                WHEN status IN ('pending', 'allocated', 'picking', 'picked', 'packing', 'packed')
                THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN status = 'shipped' AND shipped_date >= :today_start
                THEN 1 ELSE 0 END) AS shipped_today,
              SUM(CASE
                WHEN status = 'shipped' AND shipped_date >= :last_7d_start
                THEN 1 ELSE 0 END) AS shipped_7d
            FROM outbound_orders
            WHERE tenant_id = :tenant_id
              AND (
                status IN ('pending', 'allocated', 'picking', 'picked', 'packing', 'packed')
                OR (status = 'shipped' AND shipped_date >= :last_7d_start)
              )
            """,
            dashboard_params,
        ),
        (
            "dashboard_inventory_metrics_tenant",
            """
            SELECT
              COUNT(DISTINCT sku_id) AS total_skus,
              SUM(quantity_on_hand) AS total_units,
              COUNT(DISTINCT location_id) AS locations_used
            FROM inventory
            WHERE tenant_id = :tenant_id
              AND quantity_on_hand > 0
            """,
            dashboard_params,
        ),
        (
            "dashboard_task_metrics_tenant",
            """
            SELECT
              SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN status = 'completed' AND completed_at >= :today_start
                THEN 1 ELSE 0 END) AS completed_today
            FROM tasks
            WHERE tenant_id = :tenant_id
              AND (
                status = 'pending'
                OR (status = 'completed' AND completed_at >= :today_start)
              )
            """,
            dashboard_params,
        ),
        (
            "dashboard_inbound_metrics_tenant",
            """
            SELECT
              SUM(CASE
                WHEN status IN ('expected', 'arrived', 'receiving')
                THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN received_date >= :today_start
                THEN 1 ELSE 0 END) AS received_today
            FROM inbound_orders
            WHERE tenant_id = :tenant_id
              AND (
                status IN ('expected', 'arrived', 'receiving')
                OR received_date >= :today_start
              )
            """,
            dashboard_params,
        ),
        (
            "dashboard_outbound_metrics_warehouse",
            f"""
            SELECT
              SUM(CASE
                WHEN status IN ('pending', 'allocated', 'picking', 'picked', 'packing', 'packed')
                THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN status = 'shipped' AND shipped_date >= :today_start
                THEN 1 ELSE 0 END) AS shipped_today,
              SUM(CASE
                WHEN status = 'shipped' AND shipped_date >= :last_7d_start
                THEN 1 ELSE 0 END) AS shipped_7d
            FROM outbound_orders
            WHERE tenant_id = :tenant_id
              {warehouse_filter}
              AND (
                status IN ('pending', 'allocated', 'picking', 'picked', 'packing', 'packed')
                OR (status = 'shipped' AND shipped_date >= :last_7d_start)
              )
            """,
            dashboard_params,
        ),
        (
            "dashboard_inventory_metrics_warehouse",
            f"""
            SELECT
              COUNT(DISTINCT sku_id) AS total_skus,
              SUM(quantity_on_hand) AS total_units,
              COUNT(DISTINCT location_id) AS locations_used
            FROM inventory
            WHERE tenant_id = :tenant_id
              {warehouse_filter}
              AND quantity_on_hand > 0
            """,
            dashboard_params,
        ),
        (
            "dashboard_task_metrics_warehouse",
            f"""
            SELECT
              SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN status = 'completed' AND completed_at >= :today_start
                THEN 1 ELSE 0 END) AS completed_today
            FROM tasks
            WHERE tenant_id = :tenant_id
              {warehouse_filter}
              AND (
                status = 'pending'
                OR (status = 'completed' AND completed_at >= :today_start)
              )
            """,
            dashboard_params,
        ),
        (
            "dashboard_inbound_metrics_warehouse",
            f"""
            SELECT
              SUM(CASE
                WHEN status IN ('expected', 'arrived', 'receiving')
                THEN 1 ELSE 0 END) AS pending,
              SUM(CASE
                WHEN received_date >= :today_start
                THEN 1 ELSE 0 END) AS received_today
            FROM inbound_orders
            WHERE tenant_id = :tenant_id
              {warehouse_filter}
              AND (
                status IN ('expected', 'arrived', 'receiving')
                OR received_date >= :today_start
              )
            """,
            dashboard_params,
        ),
    ]


def _format_plan_row(row) -> str:
    values = tuple(row)
    if len(values) >= 4 and isinstance(values[3], str):
        return values[3]
    return " | ".join(str(value) for value in values)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", help="Tenant id to use. Defaults to the first tenant.")
    parser.add_argument("--analyze", action="store_true", help="Run EXPLAIN ANALYZE.")
    args = parser.parse_args()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    engine.echo = False
    dialect = engine.sync_engine.dialect.name

    context = await _choose_context(args.tenant_id)
    if not context["tenant_id"]:
        raise SystemExit("No tenant found. Seed data before checking query plans.")

    print(f"DATABASE_URL driver: {settings.DATABASE_URL.split(':', 1)[0]}")
    print(f"Dialect: {dialect}")
    print(f"Tenant: {context['tenant_id']}")
    print(f"Warehouse: {context['warehouse_id'] or '-'}")
    print(f"SKU: {context['sku_id'] or '-'}")

    prefix = _explain_prefix(dialect, args.analyze)
    async with engine.connect() as conn:
        for name, sql, params in _queries(context):
            print(f"\n=== {name} ===")
            result = await conn.execute(text(f"{prefix} {sql}"), params)
            for row in result:
                print(_format_plan_row(row))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
