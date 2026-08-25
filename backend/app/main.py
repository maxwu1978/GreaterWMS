"""WMS QuickStart — FastAPI application entry point."""

from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from app.models import Base
from app.models.subscription import PlanTier
from app.websocket.agv_dispatch import agv_websocket
from app.websocket.scanner import scanner_websocket

# Frontend dist directory
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


DEFAULT_PLAN_TIERS = [
    {
        "id": "plan-starter",
        "name": "Starter",
        "code": "starter",
        "price_monthly": Decimal("149"),
        "price_yearly": Decimal("1490"),
        "max_clients": 5,
        "max_skus": 1000,
        "max_orders_per_day": 200,
        "max_users": 5,
        "max_warehouses": 1,
        "trial_days": 14,
        "sort_order": 1,
        "features": {
            "shopify": False,
            "amazon": False,
            "agv": False,
            "portal": True,
            "api_full": False,
        },
    },
    {
        "id": "plan-growth",
        "name": "Growth",
        "code": "growth",
        "price_monthly": Decimal("399"),
        "price_yearly": Decimal("3990"),
        "max_clients": 20,
        "max_skus": 10000,
        "max_orders_per_day": 2000,
        "max_users": 20,
        "max_warehouses": 3,
        "trial_days": 14,
        "sort_order": 2,
        "features": {
            "shopify": True,
            "amazon": True,
            "agv": False,
            "portal": True,
            "api_full": True,
        },
    },
    {
        "id": "plan-enterprise",
        "name": "Enterprise",
        "code": "enterprise",
        "price_monthly": Decimal("899"),
        "price_yearly": Decimal("8990"),
        "max_clients": 999999,
        "max_skus": 999999,
        "max_orders_per_day": 999999,
        "max_users": 999999,
        "max_warehouses": 999999,
        "trial_days": 30,
        "sort_order": 3,
        "features": {
            "shopify": True,
            "amazon": True,
            "agv": True,
            "portal": True,
            "api_full": True,
        },
    },
]


INBOUND_PUTAWAY_TASK_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_inbound_putaway_handling_unit
ON tasks (tenant_id, task_type, reference_type, reference_id, handling_unit_id)
WHERE task_type = 'putaway'
  AND reference_type = 'inbound_order'
  AND reference_id IS NOT NULL
  AND handling_unit_id IS NOT NULL
"""

INBOUND_LIST_INDEX_SQL_STATEMENTS = [
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_orders_tenant_created
    ON inbound_orders (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_orders_tenant_status_created
    ON inbound_orders (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_order_lines_tenant_order
    ON inbound_order_lines (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inbound_packages_tenant_order_status
    ON inbound_packages (tenant_id, order_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_receiving_labels_tenant_order_status
    ON receiving_labels (tenant_id, order_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_receiving_observed_codes_tenant_order
    ON receiving_observed_codes (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_handling_units_tenant_order
    ON handling_units (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_transactions_tenant_reference
    ON inventory_transactions (tenant_id, reference_type, reference_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_reference
    ON tasks (tenant_id, reference_type, reference_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_queue
    ON tasks (tenant_id, status, task_type, assigned_type, warehouse_id, priority, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_location_sku
    ON inventory (tenant_id, warehouse_id, location_id, sku_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_created
    ON outbound_orders (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_created
    ON outbound_orders (tenant_id, warehouse_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_status_created
    ON outbound_orders (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_status_created
    ON outbound_orders (tenant_id, warehouse_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_pick_readiness_created_desc
    ON outbound_orders (tenant_id, pick_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_pick_readiness_created_desc
    ON outbound_orders (tenant_id, warehouse_id, pick_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_shipping_readiness_created_desc
    ON outbound_orders (tenant_id, shipping_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_orders_tenant_warehouse_shipping_readiness_created_desc
    ON outbound_orders (tenant_id, warehouse_id, shipping_readiness_rank, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_order_lines_tenant_order
    ON outbound_order_lines (tenant_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_outbound_order_lines_tenant_sku_order
    ON outbound_order_lines (tenant_id, sku_id, order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_tasks_tenant_status_type_priority_created
    ON tasks (tenant_id, status, task_type, priority, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_sku
    ON inventory (tenant_id, warehouse_id, sku_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_live_order
    ON inventory (tenant_id, warehouse_id, sku_id, location_id, lot_number, id)
    WHERE quantity_on_hand > 0
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_warehouse_live_metrics
    ON inventory (tenant_id, warehouse_id, sku_id, location_id, quantity_on_hand)
    WHERE quantity_on_hand > 0
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_inventory_tenant_live_metrics
    ON inventory (tenant_id, sku_id, location_id, warehouse_id, quantity_on_hand)
    WHERE quantity_on_hand > 0
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_created
    ON invoices (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_status_created
    ON invoices (tenant_id, status, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_invoices_tenant_client_created
    ON invoices (tenant_id, client_id, created_at)
    """,
]

AGENT_EVIDENCE_INDEX_SQL_STATEMENTS = [
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_evidence_token
    ON agent_evidence (tenant_id, confirmation_token_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_id
    ON agent_evidence (tenant_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_action_status
    ON agent_evidence (tenant_id, action, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_agent_evidence_tenant_payload
    ON agent_evidence (tenant_id, payload_hash)
    """,
]

WCS_TASK_BINDING_INDEX_SQL_STATEMENTS = [
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_wcs_binding_tenant_task
    ON wcs_task_bindings (tenant_id, task_id)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_wcs_binding_tenant_wcs_task
    ON wcs_task_bindings (tenant_id, wcs_task_id)
    WHERE wcs_task_id IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_wcs_task_bindings_tenant_id
    ON wcs_task_bindings (tenant_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_wcs_bindings_tenant_status
    ON wcs_task_bindings (tenant_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_wcs_bindings_tenant_psn
    ON wcs_task_bindings (tenant_id, task_psn)
    """,
]

AGENT_SCHEMA_RLS_TABLES = ("agent_evidence", "wcs_task_bindings")
PACK_LIST_SCHEMA_RLS_TABLES = ("pack_list_documents", "pack_list_lines")
MAILTASK_SCHEMA_RLS_TABLES = (
    "mail_messages",
    "mail_task_groups",
    "mail_tasks",
    "mail_attachments",
    "mail_task_approvals",
)


async def _ensure_postgres_tenant_rls(conn, table_name: str) -> None:
    await conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    await conn.execute(text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    await conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}"))
    await conn.execute(text(f"DROP POLICY IF EXISTS admin_bypass ON {table_name}"))
    await conn.execute(
        text(
            f"""
            CREATE POLICY tenant_isolation ON {table_name}
                USING (tenant_id::text = current_setting('app.current_tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE POLICY admin_bypass ON {table_name}
                USING (current_setting('app.is_platform_admin', true) = 'true')
            """
        )
    )


async def seed_default_plans() -> None:
    """Idempotently seed the default plan catalog (safe on every startup)."""
    async with async_session_factory() as session:
        existing_plans = await session.scalar(select(func.count()).select_from(PlanTier))
        if existing_plans:
            return

        session.add_all([PlanTier(**plan) for plan in DEFAULT_PLAN_TIERS])
        await session.commit()


async def ensure_schema_and_seed_defaults() -> None:
    """Startup hook.

    Schema DDL below is a DEV-ONLY convenience (create_all + inline patches) gated by
    AUTO_CREATE_SCHEMA (defaults to DEBUG). Production databases are migrated by
    Alembic — docker-entrypoint.sh runs `alembic upgrade head` before the server
    starts — so migrations stay the single source of truth for indexes and RLS.
    """
    auto_create = settings.AUTO_CREATE_SCHEMA
    if auto_create is None:
        auto_create = settings.DEBUG
    if not auto_create:
        await seed_default_plans()
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        dialect = conn.engine.dialect.name

        if dialect == "postgresql":
            await conn.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
            await conn.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
            await conn.execute(text("ALTER TABLE idempotency_records ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text("ALTER TABLE idempotency_records FORCE ROW LEVEL SECURITY"))
            await conn.execute(text("DROP POLICY IF EXISTS tenant_isolation ON idempotency_records"))
            await conn.execute(text("DROP POLICY IF EXISTS admin_bypass ON idempotency_records"))
            await conn.execute(
                text(
                    """
                    CREATE POLICY tenant_isolation ON idempotency_records
                        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
                        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE POLICY admin_bypass ON idempotency_records
                        USING (current_setting('app.is_platform_admin', true) = 'true')
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT TRUE,
                    ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(128),
                    ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMPTZ,
                    ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(128),
                    ADD COLUMN IF NOT EXISTS password_reset_sent_at TIMESTAMPTZ,
                    ADD COLUMN IF NOT EXISTS job_title VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '[]'::jsonb
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE inbound_order_lines
                    ADD COLUMN IF NOT EXISTS line_number INTEGER NOT NULL DEFAULT 1,
                    ADD COLUMN IF NOT EXISTS external_tracking_number VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_carton_mark VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_customer_barcode VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS staging_location_id VARCHAR(36),
                    ADD COLUMN IF NOT EXISTS package_count INTEGER,
                    ADD COLUMN IF NOT EXISTS pallet_count INTEGER,
                    ADD COLUMN IF NOT EXISTS rent_free_days INTEGER,
                    ADD COLUMN IF NOT EXISTS measured_weight_kg NUMERIC(10, 3),
                    ADD COLUMN IF NOT EXISTS measured_length_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS measured_width_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS measured_height_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS receiving_note TEXT
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE receiving_labels
                    ADD COLUMN IF NOT EXISTS inbound_package_id VARCHAR(36),
                    ADD COLUMN IF NOT EXISTS external_tracking_number VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_carton_mark VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_customer_barcode VARCHAR(120)
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE handling_units
                    ADD COLUMN IF NOT EXISTS inbound_package_id VARCHAR(36),
                    ADD COLUMN IF NOT EXISTS staging_location_id VARCHAR(36),
                    ADD COLUMN IF NOT EXISTS external_tracking_number VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_carton_mark VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS external_customer_barcode VARCHAR(120),
                    ADD COLUMN IF NOT EXISTS measured_weight_kg NUMERIC(10, 3),
                    ADD COLUMN IF NOT EXISTS measured_length_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS measured_width_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS measured_height_cm NUMERIC(10, 2),
                    ADD COLUMN IF NOT EXISTS package_count INTEGER,
                    ADD COLUMN IF NOT EXISTS pallet_count INTEGER,
                    ADD COLUMN IF NOT EXISTS rent_free_days INTEGER,
                    ADD COLUMN IF NOT EXISTS note TEXT
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE tasks
                    ADD COLUMN IF NOT EXISTS handling_unit_id VARCHAR(36),
                    ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(20) NOT NULL DEFAULT 'human'
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE zones
                    ADD COLUMN IF NOT EXISTS zone_type VARCHAR(40),
                    ADD COLUMN IF NOT EXISTS coordinate_x NUMERIC(10, 3),
                    ADD COLUMN IF NOT EXISTS coordinate_y NUMERIC(10, 3),
                    ADD COLUMN IF NOT EXISTS coordinate_z NUMERIC(10, 3),
                    ADD COLUMN IF NOT EXISTS dimensions JSONB,
                    ADD COLUMN IF NOT EXISTS layout_metadata JSONB,
                    ADD COLUMN IF NOT EXISTS drawing_source JSONB
                    """
                )
            )
            await conn.execute(text("UPDATE zones SET zone_type = 'storage' WHERE zone_type IS NULL"))
            await conn.execute(text("ALTER TABLE zones ALTER COLUMN zone_type SET DEFAULT 'storage'"))
            await conn.execute(text("ALTER TABLE zones ALTER COLUMN zone_type SET NOT NULL"))
            await conn.execute(
                text(
                    """
                    ALTER TABLE locations
                    ADD COLUMN IF NOT EXISTS dimensions JSONB,
                    ADD COLUMN IF NOT EXISTS layout_metadata JSONB,
                    ADD COLUMN IF NOT EXISTS drawing_source JSONB,
                    ADD COLUMN IF NOT EXISTS wcs_point_metadata JSONB
                    """
                )
            )
            await conn.execute(text(INBOUND_PUTAWAY_TASK_UNIQUE_INDEX_SQL))
            for index_sql in AGENT_EVIDENCE_INDEX_SQL_STATEMENTS:
                await conn.execute(text(index_sql))
            for index_sql in WCS_TASK_BINDING_INDEX_SQL_STATEMENTS:
                await conn.execute(text(index_sql))
            for table_name in AGENT_SCHEMA_RLS_TABLES:
                await _ensure_postgres_tenant_rls(conn, table_name)
            for table_name in PACK_LIST_SCHEMA_RLS_TABLES:
                await _ensure_postgres_tenant_rls(conn, table_name)
            for table_name in MAILTASK_SCHEMA_RLS_TABLES:
                await _ensure_postgres_tenant_rls(conn, table_name)
            await conn.execute(
                text(
                    """
                    ALTER TABLE outbound_orders
                    ADD COLUMN IF NOT EXISTS pick_readiness_rank INTEGER NOT NULL DEFAULT 90,
                    ADD COLUMN IF NOT EXISTS shipping_readiness_rank INTEGER NOT NULL DEFAULT 90
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    UPDATE outbound_orders
                    SET pick_readiness_rank = CASE
                        WHEN status = 'pending' THEN 20
                        WHEN status = 'allocated' THEN 30
                        WHEN status = 'picking' THEN 40
                        WHEN status = 'picked' THEN 50
                        WHEN status = 'packing' THEN 50
                        WHEN status = 'packed' THEN 60
                        WHEN status = 'shipped' THEN 70
                        ELSE 90
                    END,
                    shipping_readiness_rank = CASE
                        WHEN status = 'packed'
                         AND COALESCE(carrier, '') <> ''
                         AND COALESCE(tracking_number, '') <> '' THEN 10
                        WHEN status = 'packed' THEN 20
                        WHEN status = 'packing' THEN 30
                        WHEN status = 'picked' THEN 40
                        WHEN status = 'shipped' THEN 70
                        ELSE 90
                    END
                    WHERE pick_readiness_rank = 90
                      AND shipping_readiness_rank = 90
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    ALTER TABLE receiving_observed_codes
                    ADD COLUMN IF NOT EXISTS inbound_package_id VARCHAR(36)
                    """
                )
            )
        elif dialect == "sqlite":
            columns = await conn.execute(text("PRAGMA table_info(users)"))
            existing = {row[1] for row in columns}
            if "is_email_verified" not in existing:
                await conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
            if "email_verification_token" not in existing:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(128)")
                )
            if "email_verification_sent_at" not in existing:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN email_verification_sent_at DATETIME")
                )
            if "password_reset_token" not in existing:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(128)")
                )
            if "password_reset_sent_at" not in existing:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN password_reset_sent_at DATETIME")
                )
            if "job_title" not in existing:
                await conn.execute(text("ALTER TABLE users ADD COLUMN job_title VARCHAR(120)"))
            if "permissions" not in existing:
                await conn.execute(text("ALTER TABLE users ADD COLUMN permissions JSON"))

            inbound_columns = await conn.execute(text("PRAGMA table_info(inbound_order_lines)"))
            inbound_existing = {row[1] for row in inbound_columns}
            if "line_number" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN line_number INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "external_tracking_number" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN external_tracking_number VARCHAR(120)"
                    )
                )
            if "external_carton_mark" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN external_carton_mark VARCHAR(120)"
                    )
                )
            if "external_customer_barcode" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN external_customer_barcode VARCHAR(120)"
                    )
                )
            if "staging_location_id" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN staging_location_id VARCHAR(36)"
                    )
                )
            if "package_count" not in inbound_existing:
                await conn.execute(
                    text("ALTER TABLE inbound_order_lines ADD COLUMN package_count INTEGER")
                )
            if "pallet_count" not in inbound_existing:
                await conn.execute(
                    text("ALTER TABLE inbound_order_lines ADD COLUMN pallet_count INTEGER")
                )
            if "rent_free_days" not in inbound_existing:
                await conn.execute(
                    text("ALTER TABLE inbound_order_lines ADD COLUMN rent_free_days INTEGER")
                )
            if "measured_weight_kg" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN measured_weight_kg NUMERIC(10, 3)"
                    )
                )
            if "measured_length_cm" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN measured_length_cm NUMERIC(10, 2)"
                    )
                )
            if "measured_width_cm" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN measured_width_cm NUMERIC(10, 2)"
                    )
                )
            if "measured_height_cm" not in inbound_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE inbound_order_lines ADD COLUMN measured_height_cm NUMERIC(10, 2)"
                    )
                )
            if "receiving_note" not in inbound_existing:
                await conn.execute(
                    text("ALTER TABLE inbound_order_lines ADD COLUMN receiving_note TEXT")
                )

            receiving_label_columns = await conn.execute(
                text("PRAGMA table_info(receiving_labels)")
            )
            receiving_label_existing = {row[1] for row in receiving_label_columns}
            if "external_tracking_number" not in receiving_label_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE receiving_labels ADD COLUMN external_tracking_number VARCHAR(120)"
                    )
                )
            if "inbound_package_id" not in receiving_label_existing:
                await conn.execute(
                    text("ALTER TABLE receiving_labels ADD COLUMN inbound_package_id VARCHAR(36)")
                )
            if "external_carton_mark" not in receiving_label_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE receiving_labels ADD COLUMN external_carton_mark VARCHAR(120)"
                    )
                )
            if "external_customer_barcode" not in receiving_label_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE receiving_labels ADD COLUMN external_customer_barcode VARCHAR(120)"
                    )
                )

            handling_unit_columns = await conn.execute(text("PRAGMA table_info(handling_units)"))
            handling_unit_existing = {row[1] for row in handling_unit_columns}
            if "inbound_package_id" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN inbound_package_id VARCHAR(36)")
                )
            if "staging_location_id" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN staging_location_id VARCHAR(36)")
                )
            if "external_tracking_number" not in handling_unit_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE handling_units ADD COLUMN external_tracking_number VARCHAR(120)"
                    )
                )
            if "external_carton_mark" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN external_carton_mark VARCHAR(120)")
                )
            if "external_customer_barcode" not in handling_unit_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE handling_units ADD COLUMN external_customer_barcode VARCHAR(120)"
                    )
                )
            if "measured_weight_kg" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN measured_weight_kg NUMERIC(10, 3)")
                )
            if "measured_length_cm" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN measured_length_cm NUMERIC(10, 2)")
                )
            if "measured_width_cm" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN measured_width_cm NUMERIC(10, 2)")
                )
            if "measured_height_cm" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN measured_height_cm NUMERIC(10, 2)")
                )
            if "package_count" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN package_count INTEGER")
                )
            if "pallet_count" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN pallet_count INTEGER")
                )
            if "rent_free_days" not in handling_unit_existing:
                await conn.execute(
                    text("ALTER TABLE handling_units ADD COLUMN rent_free_days INTEGER")
                )
            if "note" not in handling_unit_existing:
                await conn.execute(text("ALTER TABLE handling_units ADD COLUMN note TEXT"))

            task_columns = await conn.execute(text("PRAGMA table_info(tasks)"))
            task_existing = {row[1] for row in task_columns}
            if "handling_unit_id" not in task_existing:
                await conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN handling_unit_id VARCHAR(36)")
                )
            if "execution_mode" not in task_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE tasks ADD COLUMN execution_mode VARCHAR(20) NOT NULL DEFAULT 'human'"
                    )
                )
            await conn.execute(text(INBOUND_PUTAWAY_TASK_UNIQUE_INDEX_SQL))

            zone_columns = await conn.execute(text("PRAGMA table_info(zones)"))
            zone_existing = {row[1] for row in zone_columns}
            if "zone_type" not in zone_existing:
                await conn.execute(
                    text("ALTER TABLE zones ADD COLUMN zone_type VARCHAR(40) DEFAULT 'storage'")
                )
            if "coordinate_x" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN coordinate_x NUMERIC(10, 3)"))
            if "coordinate_y" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN coordinate_y NUMERIC(10, 3)"))
            if "coordinate_z" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN coordinate_z NUMERIC(10, 3)"))
            if "dimensions" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN dimensions JSON"))
            if "layout_metadata" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN layout_metadata JSON"))
            if "drawing_source" not in zone_existing:
                await conn.execute(text("ALTER TABLE zones ADD COLUMN drawing_source JSON"))
            await conn.execute(text("UPDATE zones SET zone_type = 'storage' WHERE zone_type IS NULL"))

            location_columns = await conn.execute(text("PRAGMA table_info(locations)"))
            location_existing = {row[1] for row in location_columns}
            if "dimensions" not in location_existing:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN dimensions JSON"))
            if "layout_metadata" not in location_existing:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN layout_metadata JSON"))
            if "drawing_source" not in location_existing:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN drawing_source JSON"))
            if "wcs_point_metadata" not in location_existing:
                await conn.execute(text("ALTER TABLE locations ADD COLUMN wcs_point_metadata JSON"))

            outbound_order_columns = await conn.execute(text("PRAGMA table_info(outbound_orders)"))
            outbound_order_existing = {row[1] for row in outbound_order_columns}
            if "pick_readiness_rank" not in outbound_order_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE outbound_orders ADD COLUMN pick_readiness_rank INTEGER NOT NULL DEFAULT 90"
                    )
                )
            if "shipping_readiness_rank" not in outbound_order_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE outbound_orders ADD COLUMN shipping_readiness_rank INTEGER NOT NULL DEFAULT 90"
                    )
                )
            await conn.execute(
                text(
                    """
                    UPDATE outbound_orders
                    SET pick_readiness_rank = CASE
                        WHEN status = 'pending' THEN 20
                        WHEN status = 'allocated' THEN 30
                        WHEN status = 'picking' THEN 40
                        WHEN status = 'picked' THEN 50
                        WHEN status = 'packing' THEN 50
                        WHEN status = 'packed' THEN 60
                        WHEN status = 'shipped' THEN 70
                        ELSE 90
                    END,
                    shipping_readiness_rank = CASE
                        WHEN status = 'packed'
                         AND COALESCE(carrier, '') <> ''
                         AND COALESCE(tracking_number, '') <> '' THEN 10
                        WHEN status = 'packed' THEN 20
                        WHEN status = 'packing' THEN 30
                        WHEN status = 'picked' THEN 40
                        WHEN status = 'shipped' THEN 70
                        ELSE 90
                    END
                    WHERE pick_readiness_rank = 90
                      AND shipping_readiness_rank = 90
                    """
                )
            )

            observed_code_columns = await conn.execute(
                text("PRAGMA table_info(receiving_observed_codes)")
            )
            observed_code_existing = {row[1] for row in observed_code_columns}
            if "inbound_package_id" not in observed_code_existing:
                await conn.execute(
                    text(
                        "ALTER TABLE receiving_observed_codes ADD COLUMN inbound_package_id VARCHAR(36)"
                    )
                )

        for index_sql in INBOUND_LIST_INDEX_SQL_STATEMENTS:
            await conn.execute(text(index_sql))

    await seed_default_plans()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging(debug=settings.DEBUG)
    await ensure_schema_and_seed_defaults()
    yield
    # Shutdown — close DB engine
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware (order matters: last added = first executed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.(vercel\.app|maxsmartwms\.online)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Offset", "X-Limit", "X-Returned-Count", "X-Has-More"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=200)

# API routes
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError):
    # Database unique/FK constraints (migration 016) are the last line of
    # defense; surface them as a conflict instead of a raw 500.
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "error_code": "constraint_violation",
                "message": "The request conflicts with existing data (e.g. a duplicate code or number).",
            }
        },
    )


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "build_sha": settings.APP_BUILD_SHA or settings.RENDER_GIT_COMMIT or None,
        "branch": settings.RENDER_GIT_BRANCH or None,
        "service_id": settings.RENDER_SERVICE_ID or None,
    }


# WebSocket for barcode scanner devices
@app.websocket("/ws/scanner")
async def ws_scanner(websocket):
    await scanner_websocket(websocket)


# WebSocket for AGV fleet real-time communication
@app.websocket("/ws/agv")
async def ws_agv(websocket):
    await agv_websocket(websocket)


# ─── Serve Frontend ───
# Mount static assets (JS, CSS) at /assets
if FRONTEND_DIR.exists():
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    # SPA fallback: all non-API routes serve index.html
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API, docs, health, or websocket routes
        if full_path.startswith(("api/", "health", "ws/", "openapi")):
            return HTMLResponse(status_code=404)

        # Try to serve static file first
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))

        # Otherwise serve index.html (SPA routing)
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))

        return HTMLResponse(
            "<h1>Frontend not built. Run: cd frontend && npm run build</h1>", status_code=404
        )
