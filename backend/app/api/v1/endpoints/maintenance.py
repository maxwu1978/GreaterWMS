"""Platform maintenance endpoints for controlled operational data resets."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import Table

from app.core.database import apply_session_context, get_db_session
from app.core.deps import require_role
from app.core.security import (
    TokenPayload,
    UserRole,
    create_access_token,
    default_permissions_for_role,
    hash_password,
    normalize_email,
)
from app.models import Base
from app.models.billing import RateCard
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.subscription import PlanTier, Subscription, SubscriptionStatus
from app.models.task import PickAllocation, PutawayAllocation, Task
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.email_service import email_provider_status, send_email_provider_diagnostic
from app.services.receiving_service import ReceivingService

router = APIRouter()

RESET_CONFIRMATION = "RESET_SIMULATION_DATA"
CLEAN_TEST_DATA_CONFIRMATION = "CLEAN_TEST_DATA"
RESET_CURRENT_TENANT_DEMO_CONFIRMATION = "RESET_CURRENT_TENANT_DEMO_DATA"
CLEAR_CURRENT_TENANT_DATA_CONFIRMATION = "CLEAR_CURRENT_TENANT_DATA"
BUSINESS_MODELS = [
    PutawayAllocation,
    PickAllocation,
    Task,
    InventoryTransaction,
    Inventory,
    ReceivingObservedCode,
    HandlingUnit,
    ReceivingLabel,
    InboundPackage,
    InboundOrderLine,
    InboundOrder,
]
PRESERVED_TENANT_CODES = {"PLATFORM", "GREENECOPO"}
OPERATIONAL_TABLE_NAMES = {
    "billing_line_items",
    "billing_periods",
    "handling_units",
    "inbound_order_lines",
    "inbound_orders",
    "inbound_packages",
    "inventory",
    "inventory_transactions",
    "invoices",
    "outbound_order_lines",
    "outbound_orders",
    "pick_allocations",
    "putaway_allocations",
    "receiving_labels",
    "receiving_observed_codes",
    "return_order_lines",
    "return_orders",
    "tasks",
}
TENANT_SCOPED_DELETE_ORDER = [
    "receiving_observed_codes",
    "putaway_allocations",
    "pick_allocations",
    "tasks",
    "handling_units",
    "receiving_labels",
    "inbound_packages",
    "inbound_order_lines",
    "inbound_orders",
    "outbound_order_lines",
    "outbound_orders",
    "return_order_lines",
    "return_orders",
    "billing_line_items",
    "invoices",
    "billing_periods",
    "inventory_transactions",
    "inventory",
    "kit_components",
    "kits",
    "rate_cards",
    "skus",
    "locations",
    "zones",
    "warehouses",
    "users",
    "subscriptions",
    "clients",
]
CURRENT_TENANT_DEMO_RESET_TABLE_NAMES = set(TENANT_SCOPED_DELETE_ORDER) - {
    "subscriptions",
    "users",
}
CURRENT_TENANT_DEMO_AGENT_TOOLS = [
    "settings.agent.get",
    "settings.receiving_codes.get",
    "settings.receiving_labels.get",
    "settings.users.list",
    "settings.permissions.explain",
    "settings.client_profile.get",
    "settings.billing.explain",
    "settings.warehouse_locations.list",
]


class ResetSimulationDataRequest(BaseModel):
    confirm: str = Field(..., description=f"Must equal {RESET_CONFIRMATION}")
    seed_tenant_code: str = "GREENECOPO"
    seed_count: int = Field(default=10, ge=1, le=50)
    clear_all_tenants: bool = True


class AuditTenantBootstrapRequest(BaseModel):
    company_name: str
    company_code: str = Field(..., min_length=1, max_length=30)
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=6)
    admin_name: str = "QA Test Admin"
    plan_code: str = "enterprise"
    active_days: int = Field(default=365, ge=1, le=3650)


class CleanupTestDataRequest(BaseModel):
    confirm: str = Field(..., description=f"Must equal {CLEAN_TEST_DATA_CONFIRMATION}")
    dry_run: bool = False
    preserve_tenant_codes: list[str] = Field(default_factory=lambda: sorted(PRESERVED_TENANT_CODES))
    delete_test_tenants: bool = True
    archive_test_tenants: bool = True
    clear_operational_data_for_test_tenants: bool = True
    clear_operational_data_for_preserved_tenants: bool = True


class CurrentTenantDemoResetRequest(BaseModel):
    confirm: str = Field(..., description=f"Must equal {RESET_CURRENT_TENANT_DEMO_CONFIRMATION}")


class CurrentTenantDataClearRequest(BaseModel):
    confirm: str = Field(..., description=f"Must equal {CLEAR_CURRENT_TENANT_DATA_CONFIRMATION}")
    delete_other_users: bool = True


class EmailProviderDiagnosticRequest(BaseModel):
    to_email: EmailStr


@router.get("/email-provider/status")
async def get_email_provider_status(
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
):
    """Return a safe view of the configured transactional email providers."""
    return {
        "requested_by": current_user.sub,
        "status": email_provider_status(),
    }


@router.post("/email-provider/test")
async def test_email_provider(
    body: EmailProviderDiagnosticRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
):
    """Send one diagnostic email through the configured provider chain."""
    result = await send_email_provider_diagnostic(str(body.to_email))
    return {
        "requested_by": current_user.sub,
        **result,
    }


def _normalized_codes(codes: list[str]) -> set[str]:
    return {code.strip().upper() for code in codes if code.strip()}


def _is_test_tenant(tenant: Tenant, preserve_codes: set[str]) -> bool:
    code = (tenant.code or "").strip().upper()
    if code in preserve_codes:
        return False

    name = (tenant.name or "").strip().lower()
    code_lower = code.lower()
    email = (tenant.contact_email or "").strip().lower()
    settings = tenant.settings or {}

    if isinstance(settings, dict) and settings.get("test_bootstrap"):
        return True
    if name.startswith(("accept ", "acceptance ", "action first ")):
        return True
    if "mailersend smoke" in name:
        return True
    if name in {"bad email co", "platform admin workspace"}:
        return True
    if any(marker in name for marker in ("audit", "qa", "verify", "codex", "demo", "test")):
        return True
    if email.endswith("@example.com") or email == "not-an-email":
        return True
    return code_lower.startswith(("accept", "act", "qa", "qb", "qc", "test", "demo", "codex"))


def _tenant_scoped_tables() -> list[Table]:
    tenant_scoped_by_name = {
        table.name: table
        for table in Base.metadata.sorted_tables
        if "tenant_id" in table.c
    }
    ordered_tables = [
        tenant_scoped_by_name.pop(table_name)
        for table_name in TENANT_SCOPED_DELETE_ORDER
        if table_name in tenant_scoped_by_name
    ]
    ordered_tables.extend(reversed(list(tenant_scoped_by_name.values())))
    return ordered_tables


async def _count_table_rows(
    db: AsyncSession,
    table: Table,
    tenant_ids: list[str],
) -> int:
    if not tenant_ids:
        return 0
    query = select(func.count()).select_from(table).where(table.c.tenant_id.in_(tenant_ids))
    return int(await db.scalar(query) or 0)


async def _count_tenant_scoped_tables(
    db: AsyncSession,
    tenant_ids: list[str],
    table_names: set[str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _tenant_scoped_tables():
        if table_names is not None and table.name not in table_names:
            continue
        counts[table.name] = await _count_table_rows(db, table, tenant_ids)
    return counts


async def _delete_tenant_scoped_tables(
    db: AsyncSession,
    tenant_ids: list[str],
    table_names: set[str] | None = None,
) -> dict[str, int]:
    deleted: dict[str, int] = {}
    if not tenant_ids:
        return deleted
    if db.get_bind().dialect.name == "postgresql":
        # inventory_transactions is guarded by an append-only trigger (migration
        # 018); admin wipe flows are the sanctioned exception. Transaction-local.
        await db.execute(
            text("SELECT set_config('app.allow_ledger_admin_delete', 'true', true)")
        )
    for table in _tenant_scoped_tables():
        if table_names is not None and table.name not in table_names:
            continue
        try:
            condition = table.c.tenant_id.in_(tenant_ids)
            if table.name == "pick_allocations":
                outbound_orders = Base.metadata.tables.get("outbound_orders")
                outbound_order_lines = Base.metadata.tables.get("outbound_order_lines")
                if outbound_orders is not None and outbound_order_lines is not None:
                    condition = or_(
                        condition,
                        table.c.order_id.in_(
                            select(outbound_orders.c.id).where(
                                outbound_orders.c.tenant_id.in_(tenant_ids)
                            )
                        ),
                        table.c.order_line_id.in_(
                            select(outbound_order_lines.c.id).where(
                                outbound_order_lines.c.tenant_id.in_(tenant_ids)
                            )
                        ),
                    )
            result = await db.execute(delete(table).where(condition))
        except Exception as exc:  # pragma: no cover - only exercised by production schema drift
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Test data cleanup failed while deleting a tenant-scoped table",
                    "table": table.name,
                    "error": str(exc),
                },
            ) from exc
        deleted[table.name] = int(result.rowcount or 0)
    return deleted


async def _count_rows(
    db: AsyncSession,
    tenant_ids: list[str] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in BUSINESS_MODELS:
        query = select(func.count()).select_from(model)
        if tenant_ids:
            query = query.where(model.tenant_id.in_(tenant_ids))
        counts[model.__tablename__] = int(await db.scalar(query) or 0)
    return counts


async def _delete_rows(
    db: AsyncSession,
    tenant_ids: list[str] | None = None,
) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for model in BUSINESS_MODELS:
        stmt = delete(model)
        if tenant_ids:
            stmt = stmt.where(model.tenant_id.in_(tenant_ids))
        result = await db.execute(stmt)
        deleted[model.__tablename__] = int(result.rowcount or 0)
    return deleted


async def _reset_location_operational_status(
    db: AsyncSession,
    tenant_ids: list[str] | None = None,
) -> int:
    stmt = (
        update(Location)
        .where(Location.current_status != LocationStatus.BLOCKED.value)
        .values(current_status=LocationStatus.AVAILABLE.value)
    )
    if tenant_ids:
        stmt = stmt.where(Location.tenant_id.in_(tenant_ids))
    result = await db.execute(stmt)
    return int(result.rowcount or 0)


async def _resolve_seed_context(
    db: AsyncSession,
    tenant_code: str,
) -> tuple[Tenant, Warehouse, Location, Client, SKU]:
    tenant = await db.scalar(
        select(Tenant).where(Tenant.code == tenant_code, Tenant.is_active == True)  # noqa: E712
    )
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant code {tenant_code!r} was not found")

    warehouse = await db.scalar(
        select(Warehouse)
        .where(
            Warehouse.tenant_id == tenant.id,
            Warehouse.is_active == True,  # noqa: E712
        )
        .order_by(Warehouse.created_at.asc())
    )
    if not warehouse:
        raise HTTPException(status_code=400, detail="Seed tenant has no active warehouse")

    source_location = await db.scalar(
        select(Location)
        .where(
            Location.tenant_id == tenant.id,
            Location.warehouse_id == warehouse.id,
            Location.location_type.in_([LocationType.STAGING.value, LocationType.DOCK.value]),
        )
        .order_by(Location.location_type.desc(), Location.created_at.asc())
    )
    if not source_location:
        raise HTTPException(
            status_code=400,
            detail="Seed tenant needs at least one dock or staging location",
        )

    sku = await db.scalar(
        select(SKU)
        .where(SKU.tenant_id == tenant.id)
        .order_by(SKU.created_at.asc())
    )
    if not sku:
        raise HTTPException(status_code=400, detail="Seed tenant has no SKU to use")

    client = await db.scalar(
        select(Client).where(
            Client.id == sku.client_id,
            Client.tenant_id == tenant.id,
            Client.is_active == True,  # noqa: E712
        )
    )
    if not client:
        client = await db.scalar(
            select(Client)
            .where(
                Client.tenant_id == tenant.id,
                Client.is_active == True,  # noqa: E712
            )
            .order_by(Client.created_at.asc())
        )
    if not client:
        raise HTTPException(status_code=400, detail="Seed tenant has no active client")

    if sku.client_id != client.id:
        matching_sku = await db.scalar(
            select(SKU)
            .where(
                SKU.tenant_id == tenant.id,
                SKU.client_id == client.id,
            )
            .order_by(SKU.created_at.asc())
        )
        if not matching_sku:
            raise HTTPException(status_code=400, detail="Seed tenant client has no SKU to use")
        sku = matching_sku

    return tenant, warehouse, source_location, client, sku


async def _seed_current_tenant_demo_data(
    db: AsyncSession,
    tenant: Tenant,
    preserved_user_id: str,
) -> dict:
    settings = dict(tenant.settings or {})
    agent_console = dict(settings.get("agent_console") or {})
    if agent_console:
        allowed_tools = []
        for tool in list(agent_console.get("allowed_tools") or []) + CURRENT_TENANT_DEMO_AGENT_TOOLS:
            if tool not in allowed_tools:
                allowed_tools.append(tool)
        agent_console["allowed_tools"] = allowed_tools
    tenant.settings = {
        **settings,
        "business_mode": "3pl",
        "billing_profile": {
            "legal_name": tenant.name,
            "billing_email": tenant.contact_email,
            "tax_region": "us",
            "tax_label": "Sales Tax",
            "tax_rate_pct": 0,
            "payment_terms_label": "Net 15",
            "invoice_notes": "Demo billing profile for local agent validation.",
        },
        "receiving_code_rules": {
            "prefix": "RCV",
            "separator": "-",
            "include_order_number": True,
            "sequence_padding": 3,
            "uppercase": True,
        },
        "receiving_label_template": {
            "fields": [
                "order_number",
                "package_number",
                "sku_code",
                "expected_qty",
                "tracking_number",
            ],
            "show_field_labels": True,
        },
        "agent_console": agent_console,
    }

    client = Client(
        tenant_id=tenant.id,
        name="MaxSmart Demo Client",
        code="MAXSMART",
        contact_email="ops-demo@maxsmartwms.com",
        contact_phone="+1-925-555-0128",
        address={
            "street": "1990 N California Blvd",
            "city": "Walnut Creek",
            "state": "CA",
            "zip": "94596",
            "country": "US",
        },
        billing_enabled=True,
        portal_access=True,
        settings={
            "billing_profile": {
                "legal_name": "MaxSmart Demo Client LLC",
                "billing_email": "billing-demo@maxsmartwms.com",
                "payment_terms_label": "Net 15",
                "tax_region": "us",
            }
        },
    )
    db.add(client)
    await db.flush()

    warehouse = Warehouse(
        tenant_id=tenant.id,
        name="Demo Fulfillment Center",
        code="DEMO-FC",
        timezone="America/Los_Angeles",
        address={
            "street": "1800 Treat Blvd",
            "city": "Walnut Creek",
            "state": "CA",
            "zip": "94598",
            "country": "US",
            "_planner_rules": {
                "heavy_items_low": True,
                "fast_movers_front": True,
                "different_sku_slot_policy": "block",
                "lot_expiry_mismatch_policy": "warn",
            },
        },
    )
    db.add(warehouse)
    await db.flush()

    zones = [
        Zone(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            name="Receiving Dock",
            code="RCV",
            sequence=1,
        ),
        Zone(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            name="Forward Pick",
            code="FP",
            sequence=2,
            is_agv_zone=True,
        ),
        Zone(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            name="Reserve Storage",
            code="RS",
            sequence=3,
            is_agv_zone=True,
        ),
    ]
    db.add_all(zones)
    await db.flush()

    locations = [
        Location(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            zone_id=zones[0].id,
            barcode="RCV-DOCK-01",
            aisle="DOCK",
            rack="01",
            level="00",
            position="01",
            location_type=LocationType.DOCK.value,
            current_status=LocationStatus.AVAILABLE.value,
            pick_sequence=1,
        ),
        Location(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            zone_id=zones[0].id,
            barcode="RCV-STAGE-01",
            aisle="STAGE",
            rack="01",
            level="00",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
            pick_sequence=2,
        ),
        Location(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            zone_id=zones[1].id,
            barcode="FP-01-01-01-01",
            aisle="01",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
            is_agv_accessible=True,
            max_weight_kg=250,
            pick_sequence=10,
        ),
        Location(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            zone_id=zones[2].id,
            barcode="RS-02-01-01-01",
            aisle="02",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
            is_agv_accessible=True,
            max_weight_kg=800,
            pick_sequence=30,
        ),
    ]
    db.add_all(locations)

    skus = [
        SKU(
            tenant_id=tenant.id,
            client_id=client.id,
            sku_code="DEMO-TOTE-BLUE",
            name="Blue Storage Tote",
            barcode="850000000101",
            weight_kg=1.2,
            length_cm=55,
            width_cm=38,
            height_cm=32,
            units_per_case=6,
            cases_per_pallet=24,
        ),
        SKU(
            tenant_id=tenant.id,
            client_id=client.id,
            sku_code="DEMO-COFFEE-12OZ",
            name="House Coffee 12oz",
            barcode="850000000118",
            weight_kg=0.4,
            length_cm=10,
            width_cm=7,
            height_cm=18,
            requires_lot=True,
            requires_expiry=True,
            units_per_case=12,
            cases_per_pallet=80,
        ),
        SKU(
            tenant_id=tenant.id,
            client_id=client.id,
            sku_code="DEMO-LAMP-KIT",
            name="Desk Lamp Kit",
            barcode="850000000125",
            weight_kg=2.8,
            length_cm=42,
            width_cm=22,
            height_cm=18,
            units_per_case=4,
            cases_per_pallet=36,
        ),
    ]
    db.add_all(skus)

    rate_card = RateCard(
        tenant_id=tenant.id,
        client_id=client.id,
        name="Demo Standard Rate Card",
        effective_from=date.today(),
        rules={
            "storage_per_pallet_day": 0.85,
            "receiving_per_unit": 0.18,
            "pick_per_order": 2.25,
            "pick_per_line": 0.45,
            "shipping_handling_per_order": 1.5,
            "minimum_monthly": 250,
        },
        notes="Seeded by current-tenant demo data reset.",
    )
    db.add(rate_card)

    demo_users = [
        User(
            tenant_id=tenant.id,
            email="demo-operator@maxsmartwms.com",
            hashed_password=hash_password("DemoOperator2026Reset"),
            full_name="Demo Operator",
            role=UserRole.OPERATOR.value,
            job_title="Warehouse Operator",
            permissions=default_permissions_for_role(UserRole.OPERATOR),
            is_active=True,
            is_email_verified=True,
        ),
        User(
            tenant_id=tenant.id,
            email="demo-client@maxsmartwms.com",
            hashed_password=hash_password("DemoClient2026Reset"),
            full_name="Demo Client Viewer",
            role=UserRole.CLIENT_VIEWER.value,
            job_title="Client Portal User",
            permissions=default_permissions_for_role(UserRole.CLIENT_VIEWER),
            client_id=client.id,
            is_active=True,
            is_email_verified=True,
        ),
    ]
    db.add_all(demo_users)
    await db.flush()

    return {
        "tenant_id": tenant.id,
        "preserved_user_id": preserved_user_id,
        "client": {"id": client.id, "code": client.code},
        "warehouse": {"id": warehouse.id, "code": warehouse.code},
        "zones": [{"id": zone.id, "code": zone.code} for zone in zones],
        "locations": [{"id": location.id, "barcode": location.barcode} for location in locations],
        "skus": [{"id": sku.id, "sku_code": sku.sku_code} for sku in skus],
        "rate_card": {"id": rate_card.id, "name": rate_card.name},
        "users": [
            {"id": user.id, "email": user.email, "role": user.role}
            for user in demo_users
        ],
    }


async def _seed_inbound_putaway_data(
    db: AsyncSession,
    current_user_id: str,
    tenant_code: str,
    seed_count: int,
) -> dict:
    tenant, warehouse, source_location, client, sku = await _resolve_seed_context(db, tenant_code)
    service = ReceivingService(db, tenant.id)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    seeded_orders: list[dict] = []

    for index in range(1, seed_count + 1):
        quantity = 2 + (index % 4)
        order_number = f"INB-CLEAN-{stamp}-{index:02d}"
        tracking = f"TRK-CLEAN-{stamp}-{index:02d}"
        carton = f"CTN-CLEAN-{stamp}-{index:02d}"
        customer_code = f"CUS-CLEAN-{stamp}-{index:02d}"

        order = await service.create_inbound_order(
            client_id=client.id,
            warehouse_id=warehouse.id,
            order_number=order_number,
            reference_number=f"REF-CLEAN-{stamp}-{index:02d}",
            lines=[
                {
                    "sku_id": sku.id,
                    "quantity": quantity,
                    "external_tracking_number": tracking,
                    "external_carton_mark": carton,
                    "external_customer_barcode": customer_code,
                    "packages": [
                        {
                            "package_number": 1,
                            "package_type": "crate" if index % 3 == 0 else "carton",
                            "expected_qty": quantity,
                            "external_tracking_number": tracking,
                            "external_carton_mark": carton,
                            "external_customer_barcode": customer_code,
                        }
                    ],
                }
            ],
        )
        await service.start_receiving(order.id)
        await service.receive_label(
            order_id=order.id,
            label_code=tracking,
            quantity_received=quantity,
            quantity_damaged=0,
            staging_location_id=source_location.id,
            package_count=1,
            pallet_count=0,
            rent_free_days=0,
            measured_weight_kg=10 + index,
            receiving_note="Clean seeded receiving data",
            user_id=current_user_id,
        )
        completion = await service.complete_receiving(order.id, user_id=current_user_id)
        seeded_orders.append(
            {
                "order_id": order.id,
                "order_number": order_number,
                "tracking": tracking,
                "putaway_tasks": completion["created_tasks"],
                "putaway_units": completion["putaway_units"],
            }
        )

    return {
        "tenant_id": tenant.id,
        "tenant_code": tenant.code,
        "warehouse_id": warehouse.id,
        "warehouse_code": warehouse.code,
        "client_id": client.id,
        "client_code": client.code,
        "sku_id": sku.id,
        "sku_code": sku.sku_code,
        "source_location_id": source_location.id,
        "source_location_barcode": source_location.barcode,
        "orders": seeded_orders,
    }


@router.post("/test-tenant/bootstrap")
async def bootstrap_test_tenant(
    body: AuditTenantBootstrapRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a production-safe QA tenant without depending on email delivery.

    This endpoint is intentionally restricted to platform admins. It exists for
    smoke/regression scripts that need a verified, subscribed workspace and
    should not be blocked by the public registration email-verification path.
    """
    normalized_email = normalize_email(str(body.admin_email))
    normalized_code = body.company_code.strip().upper()
    today = date.today()
    period_end = today + timedelta(days=body.active_days)

    existing_tenant = await db.scalar(
        select(Tenant.id).where(
            or_(
                Tenant.code == normalized_code,
                func.lower(Tenant.contact_email) == normalized_email,
            )
        )
    )
    existing_user = await db.scalar(select(User.id).where(func.lower(User.email) == normalized_email))
    if existing_tenant or existing_user:
        raise HTTPException(status_code=400, detail="Company code or email already registered")

    plan = await db.scalar(
        select(PlanTier).where(
            PlanTier.code == body.plan_code,
            PlanTier.is_active == True,  # noqa: E712
        )
    )
    if not plan:
        raise HTTPException(status_code=400, detail=f"Plan '{body.plan_code}' not found")

    tenant = Tenant(
        name=body.company_name,
        code=normalized_code,
        contact_email=normalized_email,
        plan_tier=plan.code,
        is_active=True,
        settings={
            "test_bootstrap": {
                "created_by": current_user.sub,
                "created_at": datetime.now(UTC).isoformat(),
                "source": "maintenance.test-tenant.bootstrap",
            },
            "legal_acceptance": {
                "terms_accepted": True,
                "risk_notice_accepted": True,
                "accepted_at": datetime.now(UTC).isoformat(),
            },
        },
    )
    db.add(tenant)
    await db.flush()

    permissions = default_permissions_for_role(UserRole.TENANT_ADMIN)
    user = User(
        tenant_id=tenant.id,
        email=normalized_email,
        hashed_password=hash_password(body.admin_password),
        full_name=body.admin_name,
        role=UserRole.TENANT_ADMIN.value,
        permissions=permissions,
        is_active=True,
        is_email_verified=True,
        email_verification_token=None,
        email_verification_sent_at=None,
    )
    db.add(user)

    subscription = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
        trial_end_date=None,
        current_period_start=today,
        current_period_end=period_end,
    )
    db.add(subscription)
    await db.flush()

    token = create_access_token(
        user_id=user.id,
        role=UserRole.TENANT_ADMIN,
        tenant_id=tenant.id,
        permissions=permissions,
    )

    return {
        "success": True,
        "tenant_id": tenant.id,
        "tenant_code": tenant.code,
        "user_id": user.id,
        "email": user.email,
        "role": UserRole.TENANT_ADMIN.value,
        "permissions": permissions,
        "access_token": token,
        "plan": plan.code,
        "subscription_status": SubscriptionStatus.ACTIVE.value,
        "period_end": period_end.isoformat(),
        "verification_required": False,
    }


@router.post("/test-data/cleanup")
async def cleanup_test_data(
    body: CleanupTestDataRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Remove QA/test workspaces and reset operational rows before full regression testing.

    The cleanup is intentionally conservative:
    - PLATFORM and GREENECOPO are preserved by default.
    - Test workspaces are identified by explicit bootstrap metadata plus the same
      @example.com / QA / demo naming rules used by the platform UI filters.
    - Test workspaces can be hard-deleted or archived when legacy foreign keys
      make hard deletion unsafe.
    - Operational rows can be cleared for preserved tenants while keeping users,
      clients, SKUs, warehouses, locations, rate cards, and subscriptions.
    """
    if body.confirm != CLEAN_TEST_DATA_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Invalid cleanup confirmation")

    await apply_session_context(db, is_platform_admin=True)

    preserve_codes = _normalized_codes(body.preserve_tenant_codes) | PRESERVED_TENANT_CODES
    tenants = (await db.execute(select(Tenant))).scalars().all()
    active_tenants = [tenant for tenant in tenants if tenant.is_active]
    test_tenants = [tenant for tenant in active_tenants if _is_test_tenant(tenant, preserve_codes)]
    preserved_tenants = [
        tenant
        for tenant in active_tenants
        if tenant.id not in {test_tenant.id for test_tenant in test_tenants}
    ]
    test_tenant_ids = [tenant.id for tenant in test_tenants]
    preserved_tenant_ids = [tenant.id for tenant in preserved_tenants]

    test_before = await _count_tenant_scoped_tables(db, test_tenant_ids)
    preserved_operational_before = await _count_tenant_scoped_tables(
        db,
        preserved_tenant_ids,
        OPERATIONAL_TABLE_NAMES,
    )

    deleted_test_rows: dict[str, int] = {}
    deleted_test_tenants = 0
    archived_test_tenants = 0
    disabled_test_users = 0
    deleted_test_operational_rows: dict[str, int] = {}
    deleted_preserved_operational_rows: dict[str, int] = {}
    reset_locations = 0

    if not body.dry_run:
        if body.delete_test_tenants:
            deleted_test_rows = await _delete_tenant_scoped_tables(db, test_tenant_ids)
            try:
                result = await db.execute(delete(Tenant).where(Tenant.id.in_(test_tenant_ids)))
            except Exception as exc:  # pragma: no cover - only exercised by production schema drift
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Test data cleanup failed while deleting tenant records",
                        "table": "tenants",
                        "error": str(exc),
                    },
                ) from exc
            deleted_test_tenants = int(result.rowcount or 0)
        else:
            if body.clear_operational_data_for_test_tenants:
                deleted_test_operational_rows = await _delete_tenant_scoped_tables(
                    db,
                    test_tenant_ids,
                    OPERATIONAL_TABLE_NAMES,
                )
            if body.archive_test_tenants and test_tenant_ids:
                user_result = await db.execute(
                    update(User)
                    .where(User.tenant_id.in_(test_tenant_ids))
                    .values(is_active=False)
                )
                tenant_result = await db.execute(
                    update(Tenant)
                    .where(Tenant.id.in_(test_tenant_ids))
                    .values(is_active=False)
                )
                disabled_test_users = int(user_result.rowcount or 0)
                archived_test_tenants = int(tenant_result.rowcount or 0)

        if body.clear_operational_data_for_preserved_tenants:
            deleted_preserved_operational_rows = await _delete_tenant_scoped_tables(
                db,
                preserved_tenant_ids,
                OPERATIONAL_TABLE_NAMES,
            )
            reset_locations = await _reset_location_operational_status(db, preserved_tenant_ids)
        try:
            await db.commit()
        except Exception as exc:  # pragma: no cover - only exercised by production schema drift
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Test data cleanup failed while committing database changes",
                    "table": "commit",
                    "error": str(exc),
                },
            ) from exc

    test_after = await _count_tenant_scoped_tables(db, test_tenant_ids)
    preserved_operational_after = await _count_tenant_scoped_tables(
        db,
        preserved_tenant_ids,
        OPERATIONAL_TABLE_NAMES,
    )

    return {
        "dry_run": body.dry_run,
        "requested_by": current_user.sub,
        "preserve_tenant_codes": sorted(preserve_codes),
        "test_tenant_candidates": len(test_tenants),
        "preserved_tenants": [
            {
                "id": tenant.id,
                "name": tenant.name,
                "code": tenant.code,
                "contact_email": tenant.contact_email,
            }
            for tenant in sorted(preserved_tenants, key=lambda item: item.code)
        ],
        "test_tenant_examples": [
            {
                "id": tenant.id,
                "name": tenant.name,
                "code": tenant.code,
                "contact_email": tenant.contact_email,
            }
            for tenant in sorted(
                test_tenants,
                key=lambda item: (item.created_at.isoformat() if item.created_at else ""),
            )[:20]
        ],
        "before": {
            "test_tenant_rows": test_before,
            "preserved_operational_rows": preserved_operational_before,
        },
        "deleted": {
            "test_tenants": deleted_test_tenants,
            "archived_test_tenants": archived_test_tenants,
            "disabled_test_users": disabled_test_users,
            "test_tenant_rows": deleted_test_rows,
            "test_operational_rows": deleted_test_operational_rows,
            "preserved_operational_rows": deleted_preserved_operational_rows,
            "location_statuses_reset": reset_locations,
        },
        "after": {
            "test_tenant_rows": test_after,
            "preserved_operational_rows": preserved_operational_after,
        },
    }


@router.post("/current-tenant/demo-data/reset")
async def reset_current_tenant_demo_data(
    body: CurrentTenantDemoResetRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Reset the signed-in tenant's experimental business data and seed a clean demo set.

    This keeps users, subscriptions, and the tenant record intact. It is intended
    for tenant-owned demo workspaces, not platform-wide maintenance.
    """
    if body.confirm != RESET_CURRENT_TENANT_DEMO_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Invalid demo reset confirmation")
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    tenant = await db.scalar(select(Tenant).where(Tenant.id == current_user.tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_ids = [tenant.id]
    before = await _count_tenant_scoped_tables(
        db,
        tenant_ids,
        CURRENT_TENANT_DEMO_RESET_TABLE_NAMES,
    )
    deleted = await _delete_tenant_scoped_tables(
        db,
        tenant_ids,
        CURRENT_TENANT_DEMO_RESET_TABLE_NAMES,
    )
    deleted_other_users = await db.execute(
        delete(User).where(
            User.tenant_id == tenant.id,
            User.id != current_user.sub,
        )
    )
    seeded = await _seed_current_tenant_demo_data(db, tenant, current_user.sub)
    # Single unit-of-work: get_db_session commits once at request end, so a failure
    # below rolls back the whole reset instead of leaving it half-applied.
    after = await _count_tenant_scoped_tables(
        db,
        tenant_ids,
        CURRENT_TENANT_DEMO_RESET_TABLE_NAMES,
    )

    return {
        "success": True,
        "tenant_id": tenant.id,
        "tenant_code": tenant.code,
        "before": before,
        "deleted": deleted,
        "deleted_other_users": int(deleted_other_users.rowcount or 0),
        "seeded": seeded,
        "after": after,
        "preserved": ["tenant", "current_user", "subscriptions"],
    }


@router.post("/current-tenant/data/clear")
async def clear_current_tenant_data(
    body: CurrentTenantDataClearRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.TENANT_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Clear the signed-in tenant's business and setup data without seeding replacements.

    This keeps the tenant record, current signed-in user, and subscription intact so
    a test account can return to an empty workspace and continue logging in.
    """
    if body.confirm != CLEAR_CURRENT_TENANT_DATA_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Invalid current tenant clear confirmation")
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Current user is not scoped to a tenant")

    tenant = await db.scalar(select(Tenant).where(Tenant.id == current_user.tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_ids = [tenant.id]
    table_names = {
        table.name
        for table in _tenant_scoped_tables()
        if table.name not in {"users", "subscriptions"}
    }
    before = await _count_tenant_scoped_tables(db, tenant_ids, table_names)
    other_users_before = int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant.id, User.id != current_user.sub)
        )
        or 0
    )
    deleted = await _delete_tenant_scoped_tables(db, tenant_ids, table_names)
    deleted_other_users = 0
    if body.delete_other_users:
        user_result = await db.execute(
            delete(User).where(User.tenant_id == tenant.id, User.id != current_user.sub)
        )
        deleted_other_users = int(user_result.rowcount or 0)

    # Single unit-of-work: commit happens once in get_db_session at request end.
    after = await _count_tenant_scoped_tables(db, tenant_ids, table_names)
    other_users_after = int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant.id, User.id != current_user.sub)
        )
        or 0
    )

    return {
        "success": True,
        "tenant_id": tenant.id,
        "tenant_code": tenant.code,
        "before": before,
        "deleted": {
            "tenant_rows": deleted,
            "other_users": deleted_other_users,
        },
        "after": after,
        "other_users_before": other_users_before,
        "other_users_after": other_users_after,
        "preserved": ["tenant", "current_user", "subscriptions"],
    }


@router.post("/simulation-data/reset")
async def reset_simulation_data(
    body: ResetSimulationDataRequest,
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
    db: AsyncSession = Depends(get_db_session),
):
    if body.confirm != RESET_CONFIRMATION:
        raise HTTPException(status_code=400, detail="Invalid reset confirmation")

    tenant_ids: list[str] | None = None
    if not body.clear_all_tenants:
        tenant = await db.scalar(
            select(Tenant).where(
                Tenant.code == body.seed_tenant_code,
                Tenant.is_active == True,  # noqa: E712
            )
        )
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant code {body.seed_tenant_code!r} was not found",
            )
        tenant_ids = [tenant.id]

    before = await _count_rows(db, tenant_ids)
    deleted = await _delete_rows(db, tenant_ids)
    reset_locations = await _reset_location_operational_status(db, tenant_ids)
    seeded = await _seed_inbound_putaway_data(
        db=db,
        current_user_id=current_user.sub,
        tenant_code=body.seed_tenant_code,
        seed_count=body.seed_count,
    )
    after = await _count_rows(db, tenant_ids)

    return {
        "cleared_scope": "all_tenants" if tenant_ids is None else "seed_tenant",
        "before": before,
        "deleted": deleted,
        "location_statuses_reset": reset_locations,
        "seeded": seeded,
        "after": after,
    }
