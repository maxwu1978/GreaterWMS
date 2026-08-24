"""Regression tests: maintenance and demo/test-data reset (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.maintenance import (
    CLEAN_TEST_DATA_CONFIRMATION,
    CLEAR_CURRENT_TENANT_DATA_CONFIRMATION,
    RESET_CONFIRMATION,
    RESET_CURRENT_TENANT_DEMO_CONFIRMATION,
    CleanupTestDataRequest,
    CurrentTenantDataClearRequest,
    CurrentTenantDemoResetRequest,
    ResetSimulationDataRequest,
    cleanup_test_data,
    clear_current_tenant_data,
    reset_current_tenant_demo_data,
    reset_simulation_data,
)
from app.core.security import TokenPayload, UserRole, hash_password
from app.models.agent_evidence import AgentEvidence
from app.models.client import Client
from app.models.idempotency import IdempotencyRecord
from app.models.inventory import SKU, Inventory
from app.models.order import (
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
)
from app.models.subscription import PlanTier, Subscription, SubscriptionStatus
from app.models.task import AssignedType, PickAllocation, Task, TaskStatus, TaskType
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone


@pytest.mark.asyncio
async def test_reset_simulation_data_rebuilds_clean_putaway_records(
    db: AsyncSession,
    user_id: str,
):
    seed_tenant_id = "tenant-clean-001"
    seed_client_id = "client-clean-001"
    seed_warehouse_id = "warehouse-clean-001"
    seed_sku_id = "sku-clean-001"
    source_location_id = "staging-clean-001"
    other_tenant_id = "tenant-old-002"

    db.add(
        Tenant(
            id=seed_tenant_id,
            name="GreenEcoPower",
            code="GREENECOPO",
            contact_email="clean@example.com",
        )
    )
    db.add(Client(id=seed_client_id, tenant_id=seed_tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=seed_warehouse_id, tenant_id=seed_tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-clean-001",
            tenant_id=seed_tenant_id,
            warehouse_id=seed_warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id=source_location_id,
            tenant_id=seed_tenant_id,
            warehouse_id=seed_warehouse_id,
            zone_id="zone-clean-001",
            barcode="STAGE-CLEAN-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        Location(
            id="blocked-clean-001",
            tenant_id=seed_tenant_id,
            warehouse_id=seed_warehouse_id,
            zone_id="zone-clean-001",
            barcode="BLOCKED-CLEAN-01",
            aisle="BLOCK",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.BLOCKED.value,
        )
    )
    db.add(
        SKU(
            id=seed_sku_id,
            tenant_id=seed_tenant_id,
            client_id=seed_client_id,
            sku_code="DAN-CLEAN-001",
            name="Clean Seed SKU",
        )
    )
    db.add(
        Tenant(
            id=other_tenant_id,
            name="Old Tenant",
            code="OLD",
            contact_email="old@example.com",
        )
    )
    db.add(
        InboundOrder(
            id="old-inbound-001",
            tenant_id=seed_tenant_id,
            client_id=seed_client_id,
            warehouse_id=seed_warehouse_id,
            order_number="OLD-INB-001",
            status=InboundStatus.PUTAWAY.value,
        )
    )
    db.add(
        InboundOrderLine(
            id="old-line-001",
            tenant_id=seed_tenant_id,
            order_id="old-inbound-001",
            sku_id=seed_sku_id,
            line_number=1,
            quantity_expected=1,
        )
    )
    db.add(
        InboundPackage(
            id="old-package-001",
            tenant_id=seed_tenant_id,
            order_id="old-inbound-001",
            order_line_id="old-line-001",
            package_number=1,
            status=InboundPackageStatus.PUTAWAY_PENDING.value,
            expected_qty=1,
        )
    )
    db.add(
        Task(
            id="old-task-001",
            tenant_id=seed_tenant_id,
            warehouse_id=seed_warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id=seed_sku_id,
            quantity=1,
            reference_type="inbound_order",
            reference_id="old-inbound-001",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    db.add(
        InboundOrder(
            id="old-inbound-002",
            tenant_id=other_tenant_id,
            client_id=seed_client_id,
            warehouse_id=seed_warehouse_id,
            order_number="OLD-INB-002",
            status=InboundStatus.EXPECTED.value,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    result = await reset_simulation_data(
        ResetSimulationDataRequest(
            confirm=RESET_CONFIRMATION,
            seed_tenant_code="GREENECOPO",
            seed_count=3,
            clear_all_tenants=True,
        ),
        current_user=current_user,
        db=db,
    )

    assert result["cleared_scope"] == "all_tenants"
    assert result["deleted"]["inbound_orders"] == 2
    assert result["seeded"]["tenant_code"] == "GREENECOPO"
    assert len(result["seeded"]["orders"]) == 3
    assert result["after"]["inbound_orders"] == 3
    assert result["after"]["inbound_packages"] == 3
    assert result["after"]["receiving_labels"] == 3
    assert result["after"]["handling_units"] == 3
    assert result["after"]["tasks"] == 3
    assert result["after"]["inventory_transactions"] == 3
    assert result["after"]["inventory"] == 1

    orders = (
        (await db.execute(select(InboundOrder).order_by(InboundOrder.order_number.asc())))
        .scalars()
        .all()
    )
    packages = (await db.execute(select(InboundPackage))).scalars().all()
    tasks = (await db.execute(select(Task).order_by(Task.created_at.asc()))).scalars().all()
    inventory = await db.scalar(select(Inventory))
    source_location = await db.scalar(select(Location).where(Location.id == source_location_id))
    blocked_location = await db.scalar(select(Location).where(Location.id == "blocked-clean-001"))

    assert all(order.order_number.startswith("INB-CLEAN-") for order in orders)
    assert all(order.status == InboundStatus.PUTAWAY.value for order in orders)
    assert all(package.status == InboundPackageStatus.PUTAWAY_PENDING.value for package in packages)
    assert all(task.task_type == TaskType.PUTAWAY.value for task in tasks)
    assert all(task.source_location_id == source_location_id for task in tasks)
    assert inventory.quantity_on_hand == 12
    assert source_location.current_status == LocationStatus.AVAILABLE.value
    assert blocked_location.current_status == LocationStatus.BLOCKED.value


@pytest.mark.asyncio
async def test_current_tenant_demo_reset_clears_business_data_and_preserves_users(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Demo Reset Tenant",
            code="DRT",
            contact_email="demo-reset@example.com",
            settings={"agent_console": {"enabled": True, "allowed_tools": ["settings.agent.get"]}},
        )
    )
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email="demo-admin@example.com",
            hashed_password="hash",
            full_name="Demo Admin",
            role=UserRole.TENANT_ADMIN.value,
            permissions=["users.manage"],
        )
    )
    db.add(
        User(
            id="old-demo-user",
            tenant_id=tenant_id,
            email="old-demo-user@example.com",
            hashed_password="hash",
            full_name="Old Demo User",
            role=UserRole.OPERATOR.value,
            permissions=["receiving.execute"],
        )
    )
    db.add(
        PlanTier(
            id="plan-demo-reset",
            name="Demo Reset Plan",
            code="demo-reset",
            price_monthly=0,
            price_yearly=0,
        )
    )
    db.add(
        Subscription(
            id="demo-reset-sub",
            tenant_id=tenant_id,
            plan_id="plan-demo-reset",
            status=SubscriptionStatus.ACTIVE.value,
        )
    )
    db.add(Client(id="old-demo-client", tenant_id=tenant_id, name="Old Client", code="OLD"))
    db.add(Warehouse(id="old-demo-warehouse", tenant_id=tenant_id, name="Old WH", code="OLDWH"))
    db.add(
        Zone(
            id="old-demo-zone",
            tenant_id=tenant_id,
            warehouse_id="old-demo-warehouse",
            name="Old Zone",
            code="OLD",
        )
    )
    db.add(
        Location(
            id="old-demo-location",
            tenant_id=tenant_id,
            warehouse_id="old-demo-warehouse",
            zone_id="old-demo-zone",
            barcode="OLD-01",
            aisle="01",
            rack="01",
            level="01",
            position="01",
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["users.manage"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    result = await reset_current_tenant_demo_data(
        CurrentTenantDemoResetRequest(confirm=RESET_CURRENT_TENANT_DEMO_CONFIRMATION),
        current_user=current_user,
        db=db,
    )

    assert result["success"] is True
    assert result["deleted"]["clients"] == 1
    assert result["deleted_other_users"] == 1
    assert result["seeded"]["client"]["code"] == "MAXSMART"
    assert len(result["seeded"]["skus"]) == 3
    assert len(result["seeded"]["users"]) == 2
    assert result["preserved"] == ["tenant", "current_user", "subscriptions"]

    assert await db.scalar(select(User).where(User.id == user_id))
    assert await db.scalar(select(Subscription).where(Subscription.id == "demo-reset-sub"))
    assert await db.scalar(select(Client).where(Client.code == "MAXSMART"))
    assert await db.scalar(select(Warehouse).where(Warehouse.code == "DEMO-FC"))
    assert await db.scalar(select(User).where(User.email == "demo-operator@maxsmartwms.com"))
    assert not await db.scalar(select(User).where(User.id == "old-demo-user"))
    assert not await db.scalar(select(Client).where(Client.id == "old-demo-client"))
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant.settings["agent_console"]["enabled"] is True
    assert tenant.settings["receiving_code_rules"]["prefix"] == "RCV"
    assert "settings.agent.get" in tenant.settings["agent_console"]["allowed_tools"]
    assert "settings.warehouse_locations.list" in tenant.settings["agent_console"]["allowed_tools"]


@pytest.mark.asyncio
async def test_cleanup_test_data_deletes_test_workspaces_and_clears_preserved_operations(
    db: AsyncSession,
    user_id: str,
):
    preserved_tenant_id = "tenant-clean-preserve"
    preserved_client_id = "client-clean-preserve"
    preserved_warehouse_id = "warehouse-clean-preserve"
    preserved_zone_id = "zone-clean-preserve"
    preserved_location_id = "location-clean-preserve"
    preserved_sku_id = "sku-clean-preserve"
    test_tenant_id = "tenant-clean-test"

    db.add(
        Tenant(
            id=preserved_tenant_id,
            name="greenecopower",
            code="GREENECOPO",
            contact_email="wuqxmark@gmail.com",
        )
    )
    db.add(
        Client(
            id=preserved_client_id,
            tenant_id=preserved_tenant_id,
            name="Danube Foods",
            code="DANUBE",
        )
    )
    db.add(
        Warehouse(
            id=preserved_warehouse_id,
            tenant_id=preserved_tenant_id,
            name="Budapest",
            code="BUD",
        )
    )
    db.add(
        Zone(
            id=preserved_zone_id,
            tenant_id=preserved_tenant_id,
            warehouse_id=preserved_warehouse_id,
            name="Zone A",
            code="A",
        )
    )
    db.add(
        Location(
            id=preserved_location_id,
            tenant_id=preserved_tenant_id,
            warehouse_id=preserved_warehouse_id,
            zone_id=preserved_zone_id,
            barcode="A-01-01-01-01",
            aisle="01",
            rack="01",
            level="01",
            position="01",
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id=preserved_sku_id,
            tenant_id=preserved_tenant_id,
            client_id=preserved_client_id,
            sku_code="DAN-CLEAN-001",
            name="Clean SKU",
        )
    )
    db.add(
        InboundOrder(
            id="inbound-clean-preserve",
            tenant_id=preserved_tenant_id,
            client_id=preserved_client_id,
            warehouse_id=preserved_warehouse_id,
            order_number="INB-OLD-CLEAN",
            status=InboundStatus.PUTAWAY.value,
        )
    )
    db.add(
        InboundOrderLine(
            id="line-clean-preserve",
            tenant_id=preserved_tenant_id,
            order_id="inbound-clean-preserve",
            sku_id=preserved_sku_id,
            line_number=1,
            quantity_expected=1,
        )
    )
    db.add(
        Inventory(
            id="inventory-clean-preserve",
            tenant_id=preserved_tenant_id,
            client_id=preserved_client_id,
            warehouse_id=preserved_warehouse_id,
            location_id=preserved_location_id,
            sku_id=preserved_sku_id,
            quantity_on_hand=3,
        )
    )
    db.add(
        OutboundOrder(
            id="outbound-clean-preserve",
            tenant_id=preserved_tenant_id,
            client_id=preserved_client_id,
            warehouse_id=preserved_warehouse_id,
            order_number="OUT-OLD-CLEAN",
            status=OutboundStatus.PICKING.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="outbound-line-clean-preserve",
            tenant_id=preserved_tenant_id,
            order_id="outbound-clean-preserve",
            sku_id=preserved_sku_id,
            quantity_ordered=1,
        )
    )
    db.add(
        PickAllocation(
            id="pick-allocation-clean-drift",
            tenant_id="tenant-clean-drift",
            order_id="outbound-clean-preserve",
            order_line_id="outbound-line-clean-preserve",
            warehouse_id=preserved_warehouse_id,
            sku_id=preserved_sku_id,
            location_id=preserved_location_id,
            quantity=1,
        )
    )

    db.add(
        Tenant(
            id=test_tenant_id,
            name="QA Cleanup Tenant",
            code="QACLEAN",
            contact_email="qa-clean@example.com",
            settings={"test_bootstrap": {"source": "maintenance.test-tenant.bootstrap"}},
        )
    )
    db.add(
        User(
            id="user-clean-test",
            tenant_id=test_tenant_id,
            email="qa-clean-admin@example.com",
            hashed_password=hash_password("adminpass"),
            full_name="QA Cleanup Admin",
            role=UserRole.TENANT_ADMIN.value,
            is_active=True,
        )
    )
    db.add(Client(id="client-clean-test", tenant_id=test_tenant_id, name="QA Client", code="QA"))
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    result = await cleanup_test_data(
        CleanupTestDataRequest(confirm=CLEAN_TEST_DATA_CONFIRMATION),
        current_user=current_user,
        db=db,
    )

    assert result["test_tenant_candidates"] == 1
    assert result["deleted"]["test_tenants"] == 1
    assert result["deleted"]["preserved_operational_rows"]["inbound_orders"] == 1
    assert result["deleted"]["preserved_operational_rows"]["inventory"] == 1
    assert result["deleted"]["preserved_operational_rows"]["outbound_order_lines"] == 1
    assert result["deleted"]["preserved_operational_rows"]["pick_allocations"] == 1

    assert await db.scalar(select(Tenant).where(Tenant.id == test_tenant_id)) is None
    assert await db.scalar(select(User).where(User.id == "user-clean-test")) is None
    assert await db.scalar(select(Client).where(Client.id == "client-clean-test")) is None

    assert await db.scalar(select(Tenant).where(Tenant.id == preserved_tenant_id)) is not None
    assert await db.scalar(select(Client).where(Client.id == preserved_client_id)) is not None
    assert await db.scalar(select(SKU).where(SKU.id == preserved_sku_id)) is not None
    assert await db.scalar(select(InboundOrder).where(InboundOrder.id == "inbound-clean-preserve")) is None
    assert await db.scalar(select(OutboundOrder).where(OutboundOrder.id == "outbound-clean-preserve")) is None
    assert await db.scalar(select(Inventory).where(Inventory.id == "inventory-clean-preserve")) is None
    assert (
        await db.scalar(select(PickAllocation).where(PickAllocation.id == "pick-allocation-clean-drift"))
        is None
    )

    preserved_location = await db.scalar(select(Location).where(Location.id == preserved_location_id))
    assert preserved_location is not None
    assert preserved_location.current_status == LocationStatus.AVAILABLE.value


@pytest.mark.asyncio
async def test_cleanup_test_data_can_archive_active_test_workspaces(
    db: AsyncSession,
    user_id: str,
):
    test_tenant_id = "tenant-clean-archive"

    db.add(
        Tenant(
            id=test_tenant_id,
            name="QA Archive Tenant",
            code="QAARCH",
            contact_email="qa-archive@example.com",
            settings={"test_bootstrap": {"source": "maintenance.test-tenant.bootstrap"}},
        )
    )
    db.add(
        User(
            id="user-clean-archive",
            tenant_id=test_tenant_id,
            email="qa-archive-admin@example.com",
            hashed_password=hash_password("adminpass"),
            full_name="QA Archive Admin",
            role=UserRole.TENANT_ADMIN.value,
            is_active=True,
        )
    )
    db.add(Client(id="client-clean-archive", tenant_id=test_tenant_id, name="QA Client", code="QA"))
    await db.flush()

    current_user = TokenPayload(
        sub=user_id,
        role=UserRole.PLATFORM_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    result = await cleanup_test_data(
        CleanupTestDataRequest(
            confirm=CLEAN_TEST_DATA_CONFIRMATION,
            delete_test_tenants=False,
            clear_operational_data_for_preserved_tenants=False,
        ),
        current_user=current_user,
        db=db,
    )

    assert result["test_tenant_candidates"] == 1
    assert result["deleted"]["archived_test_tenants"] == 1
    assert result["deleted"]["disabled_test_users"] == 1

    tenant = await db.scalar(select(Tenant).where(Tenant.id == test_tenant_id))
    user = await db.scalar(select(User).where(User.id == "user-clean-archive"))
    client = await db.scalar(select(Client).where(Client.id == "client-clean-archive"))

    assert tenant is not None
    assert tenant.is_active is False
    assert user is not None
    assert user.is_active is False
    assert client is not None

    dry_run = await cleanup_test_data(
        CleanupTestDataRequest(
            confirm=CLEAN_TEST_DATA_CONFIRMATION,
            dry_run=True,
            delete_test_tenants=False,
            clear_operational_data_for_preserved_tenants=False,
        ),
        current_user=current_user,
        db=db,
    )

    assert dry_run["test_tenant_candidates"] == 0
    assert dry_run["test_tenant_examples"] == []


@pytest.mark.asyncio
async def test_clear_current_tenant_data_preserves_login_user_and_subscription(
    db: AsyncSession,
):
    tenant_id = "tenant-current-clear"
    current_user_id = "user-current-clear"
    other_user_id = "user-current-clear-other"
    client_id = "client-current-clear"
    warehouse_id = "warehouse-current-clear"
    zone_id = "zone-current-clear"
    location_id = "location-current-clear"
    sku_id = "sku-current-clear"

    db.add(
        Tenant(
            id=tenant_id,
            name="Current Clear Tenant",
            code="CURCLEAR",
            contact_email="current-clear@example.com",
        )
    )
    db.add(
        User(
            id=current_user_id,
            tenant_id=tenant_id,
            email="current-clear@example.com",
            hashed_password=hash_password("adminpass"),
            full_name="Current Clear Admin",
            role=UserRole.TENANT_ADMIN.value,
            is_active=True,
        )
    )
    db.add(
        User(
            id=other_user_id,
            tenant_id=tenant_id,
            email="current-clear-operator@example.com",
            hashed_password=hash_password("operatorpass"),
            full_name="Current Clear Operator",
            role=UserRole.OPERATOR.value,
            is_active=True,
        )
    )
    db.add(
        PlanTier(
            id="plan-current-clear",
            name="Current Clear Plan",
            code="current-clear",
            price_monthly=0,
            price_yearly=0,
        )
    )
    db.add(
        Subscription(
            id="subscription-current-clear",
            tenant_id=tenant_id,
            plan_id="plan-current-clear",
            status=SubscriptionStatus.ACTIVE.value,
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Clear Client", code="CLR"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Clear Warehouse", code="CLW"))
    db.add(
        Zone(
            id=zone_id,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Clear Zone",
            code="CZ",
        )
    )
    db.add(
        Location(
            id=location_id,
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id=zone_id,
            barcode="CLR-01",
            aisle="C",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id=sku_id,
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="CLR-SKU",
            name="Clear SKU",
        )
    )
    db.add(
        Inventory(
            id="inventory-current-clear",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku_id=sku_id,
            quantity_on_hand=5,
        )
    )
    db.add(
        AgentEvidence(
            id="evidence-current-clear",
            tenant_id=tenant_id,
            action="inventory.adjust",
            risk="write",
            required_permission="planner.manage",
            entity_type="inventory",
            entity_id="inventory-current-clear",
            payload_hash="payload-current-clear",
            confirmation_token_hash="token-current-clear",
            planned_endpoint="/api/v1/inventory/adjust",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    db.add(
        IdempotencyRecord(
            id="idempotency-current-clear",
            tenant_id=tenant_id,
            idempotency_key="current-clear-key",
            operation="inventory.adjust",
            request_hash="request-current-clear",
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub=current_user_id,
        role=UserRole.TENANT_ADMIN,
        tenant_id=tenant_id,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    result = await clear_current_tenant_data(
        CurrentTenantDataClearRequest(confirm=CLEAR_CURRENT_TENANT_DATA_CONFIRMATION),
        current_user=current_user,
        db=db,
    )

    assert result["success"] is True
    assert result["tenant_id"] == tenant_id
    assert result["deleted"]["tenant_rows"]["clients"] == 1
    assert result["deleted"]["tenant_rows"]["inventory"] == 1
    assert result["deleted"]["tenant_rows"]["agent_evidence"] == 1
    assert result["deleted"]["tenant_rows"]["idempotency_records"] == 1
    assert result["deleted"]["other_users"] == 1
    assert sum(result["after"].values()) == 0
    assert result["other_users_after"] == 0

    assert await db.scalar(select(Tenant).where(Tenant.id == tenant_id)) is not None
    assert await db.scalar(select(User).where(User.id == current_user_id)) is not None
    assert await db.scalar(select(User).where(User.id == other_user_id)) is None
    assert await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id)) is not None
    assert await db.scalar(select(Client).where(Client.id == client_id)) is None
    assert await db.scalar(select(Warehouse).where(Warehouse.id == warehouse_id)) is None
    assert await db.scalar(select(Inventory).where(Inventory.id == "inventory-current-clear")) is None
    assert await db.scalar(select(AgentEvidence).where(AgentEvidence.id == "evidence-current-clear")) is None
    assert (
        await db.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.id == "idempotency-current-clear")
        )
        is None
    )
