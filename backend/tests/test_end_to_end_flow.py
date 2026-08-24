"""
End-to-end test: Receive → Putaway → Pick → Pack → Ship

This test validates the complete warehouse flow without a running server,
using the service layer directly against an in-memory database.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.order import (
    HandlingUnit,
    InboundPackage,
    InboundPackageStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
    ReceivingLabel,
)
from app.models.task import Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import (
    Location,
    LocationStatus,
    LocationType,
    Warehouse,
    Zone,
)
from app.services.picking_service import PickingService
from app.services.putaway_service import PutawayService
from app.services.receiving_service import ReceivingService
from app.services.shipping_service import ShippingService


async def setup_warehouse(db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str):
    """Create test data: tenant, client, warehouse, zones, locations, SKU."""
    tenant = Tenant(id=tenant_id, name="Test 3PL", code="TST", contact_email="test@example.com")
    db.add(tenant)

    client = Client(
        id=client_id,
        tenant_id=tenant_id,
        name="Acme Corp",
        code="ACME",
    )
    db.add(client)

    warehouse = Warehouse(
        id=warehouse_id,
        tenant_id=tenant_id,
        name="DFW Warehouse",
        code="DFW1",
    )
    db.add(warehouse)

    zone = Zone(
        id="zone-a",
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        name="Zone A",
        code="A",
    )
    db.add(zone)

    # Staging location (dock)
    staging = Location(
        id="loc-staging",
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        zone_id="zone-a",
        barcode="STAGE-01",
        aisle="S",
        rack="01",
        level="01",
        position="01",
        location_type=LocationType.STAGING.value,
        current_status=LocationStatus.AVAILABLE.value,
    )
    db.add(staging)

    # Storage locations
    for i in range(1, 4):
        loc = Location(
            id=f"loc-store-{i}",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-a",
            barcode=f"A-01-{i:02d}-01-01",
            aisle="01",
            rack=f"{i:02d}",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
            pick_sequence=i,
            coordinate_x=float(i * 2),
            coordinate_y=1.0,
            coordinate_z=0.0,
            is_agv_accessible=True,
        )
        db.add(loc)

    # SKU
    sku = SKU(
        id="sku-widget",
        tenant_id=tenant_id,
        client_id=client_id,
        sku_code="WIDGET-001",
        name="Standard Widget",
        weight_kg=0.5,
        length_cm=10,
        width_cm=8,
        height_cm=5,
    )
    db.add(sku)

    await db.flush()
    return {"staging_id": "loc-staging", "sku_id": "sku-widget"}


@pytest.mark.asyncio
async def test_full_warehouse_flow(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str, user_id: str
):
    """Test the complete receive → putaway → pick → ship cycle."""

    fixtures = await setup_warehouse(db, tenant_id, client_id, warehouse_id)
    staging_id = fixtures["staging_id"]
    sku_id = fixtures["sku_id"]

    # ========== STEP 1: RECEIVING ==========
    recv_svc = ReceivingService(db, tenant_id)

    # Create inbound order (ASN)
    order = await recv_svc.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="PO-2026-001",
        lines=[{"sku_id": sku_id, "quantity": 100}],
        supplier_name="Widget Factory",
    )
    assert order.order_number == "PO-2026-001"

    # Start receiving
    order = await recv_svc.start_receiving(order.id)
    assert order.status == "receiving"

    # Get lines
    from app.models.order import InboundOrderLine

    lines_result = await db.execute(
        select(InboundOrderLine).where(InboundOrderLine.order_id == order.id)
    )
    line = lines_result.scalar_one()

    # Receive items at staging location
    receipt = await recv_svc.receive_line(
        order_id=order.id,
        line_id=line.id,
        quantity_received=98,
        quantity_damaged=2,
        staging_location_id=staging_id,
        user_id=user_id,
    )
    assert receipt["status"] == "short"
    assert receipt["discrepancy"] == -2  # expected 100, got 98
    assert receipt["label_code"]
    assert receipt["handling_unit_code"] == receipt["label_code"]
    assert receipt["handling_unit_status"] == "staged"

    label = await db.scalar(
        select(ReceivingLabel).where(
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id == order.id,
            ReceivingLabel.inbound_package_id == receipt["package_id"],
        )
    )
    assert label is not None
    assert label.status == "received"
    assert label.received_qty == 96

    handling_unit = await db.scalar(
        select(HandlingUnit).where(
            HandlingUnit.tenant_id == tenant_id,
            HandlingUnit.order_id == order.id,
            HandlingUnit.inbound_package_id == receipt["package_id"],
        )
    )
    assert handling_unit is not None
    assert handling_unit.unit_code == receipt["label_code"]
    assert handling_unit.received_qty == 96
    assert handling_unit.status == "staged"

    # Complete receiving → generates putaway tasks
    completion = await recv_svc.complete_receiving(order.id, user_id=user_id)
    order = completion["order"]
    assert order.status == "putaway"

    # Verify inventory at staging
    inv_result = await db.execute(
        select(Inventory).where(
            Inventory.location_id == staging_id,
            Inventory.sku_id == sku_id,
        )
    )
    staging_inv = inv_result.scalar_one()
    assert staging_inv.quantity_on_hand == 96  # 98 received - 2 damaged

    # Verify putaway task was created
    task_result = await db.execute(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    putaway_task = task_result.scalar_one()
    assert putaway_task.status == TaskStatus.PENDING.value
    assert putaway_task.quantity == 96
    assert putaway_task.handling_unit_id == handling_unit.id

    with pytest.raises(HTTPException) as second_completion:
        await recv_svc.complete_receiving(order.id, user_id=user_id)
    assert second_completion.value.status_code == 409
    repeated_task_result = await db.execute(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    assert len(list(repeated_task_result.scalars())) == 1

    # ========== STEP 2: PUTAWAY ==========
    putaway_svc = PutawayService(db, tenant_id)

    # Get location suggestions
    suggestions = await putaway_svc.suggest_location(warehouse_id, sku_id, 96)
    assert len(suggestions) > 0
    assert suggestions[0]["location_id"]
    assert suggestions[0]["reason"] in {"empty_available", "consolidate_with_existing_sku"}

    # Set source location on task for putaway
    putaway_task.source_location_id = staging_id
    await db.flush()

    # Confirm putaway to first suggested location
    dest_loc_id = suggestions[0]["location_id"]
    result = await putaway_svc.confirm_putaway(putaway_task.id, dest_loc_id, user_id)
    assert result["success"] is True
    assert result["quantity"] == 96

    # Verify inventory moved to storage
    store_inv_result = await db.execute(
        select(Inventory).where(
            Inventory.location_id == dest_loc_id,
            Inventory.sku_id == sku_id,
        )
    )
    store_inv = store_inv_result.scalar_one()
    assert store_inv.quantity_on_hand == 96

    # ========== STEP 3: OUTBOUND ORDER + PICKING ==========
    pick_svc = PickingService(db, tenant_id)

    # Create outbound order
    outbound = OutboundOrder(
        id="out-001",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="SO-2026-001",
        status=OutboundStatus.PENDING.value,
        priority=3,
        ship_to_name="John Doe",
        ship_to_address={"street": "123 Main St", "city": "Dallas", "state": "TX", "zip": "75001"},
    )
    db.add(outbound)

    out_line = OutboundOrderLine(
        id="out-line-001",
        tenant_id=tenant_id,
        order_id="out-001",
        sku_id=sku_id,
        quantity_ordered=20,
    )
    db.add(out_line)
    await db.flush()

    # Allocate inventory (FIFO)
    alloc = await pick_svc.allocate_order("out-001")
    assert alloc["fully_allocated"] is True
    assert alloc["lines"][0]["allocated"] == 20
    assert alloc["lines"][0]["shortage"] == 0

    # Create pick tasks
    task_ids = await pick_svc.create_pick_tasks("out-001")
    assert len(task_ids) == 1

    # Confirm pick
    pick_result = await pick_svc.confirm_pick(task_ids[0], 20, user_id)
    assert pick_result["success"] is True
    assert pick_result["remaining_at_location"] == 76  # 96 - 20

    # Verify order status advanced to PICKED
    order_result = await db.execute(select(OutboundOrder).where(OutboundOrder.id == "out-001"))
    out_order = order_result.scalar_one()
    assert out_order.status == OutboundStatus.PICKED.value

    # ========== STEP 4: PACK & SHIP ==========
    ship_svc = ShippingService(db, tenant_id)

    # Verify pack (scan items into box)
    pack_result = await ship_svc.verify_pack(
        "out-001",
        [{"sku_id": sku_id, "quantity": 20}],
        user_id,
    )
    assert pack_result["verified"] is True

    # Ship confirm
    ship_result = await ship_svc.ship_confirm(
        order_id="out-001",
        carrier="UPS",
        tracking_number="1Z999AA10123456784",
        service_level="ground",
        shipping_cost=12.50,
        user_id=user_id,
    )
    assert ship_result["status"] == "shipped"
    assert ship_result["tracking_number"] == "1Z999AA10123456784"

    # ========== VERIFY FINAL STATE ==========

    # Remaining inventory: 76 widgets at storage location
    final_inv = await db.execute(
        select(Inventory).where(
            Inventory.sku_id == sku_id,
            Inventory.quantity_on_hand > 0,
        )
    )
    remaining = final_inv.scalars().all()
    total_remaining = sum(inv.quantity_on_hand for inv in remaining)
    assert total_remaining == 76

    # Transaction audit trail should have entries for each step
    txn_result = await db.execute(
        select(InventoryTransaction).where(
            InventoryTransaction.sku_id == sku_id,
        )
    )
    txns = txn_result.scalars().all()
    txn_types = [t.transaction_type for t in txns]
    assert "receive" in txn_types
    assert "putaway" in txn_types
    assert "pick" in txn_types
    assert "ship" in txn_types

    db.add(
        Task(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            sku_id=sku_id,
            quantity=96,
            handling_unit_id=handling_unit.id,
            source_location_id=staging_id,
            reference_type="inbound_order",
            reference_id=order.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_multi_tenant_isolation(db: AsyncSession):
    """Verify that service instances only see their own tenant's data."""

    # Setup tenant A
    await setup_warehouse(db, "tenant-a", "client-a", "wh-a")
    recv_a = ReceivingService(db, "tenant-a")
    order_a = await recv_a.create_inbound_order(
        client_id="client-a",
        warehouse_id="wh-a",
        order_number="PO-A-001",
        lines=[{"sku_id": "sku-widget", "quantity": 50}],
    )

    # Setup tenant B with different data
    tenant_b = Tenant(id="tenant-b", name="Other 3PL", code="OTH", contact_email="b@example.com")
    db.add(tenant_b)
    client_b = Client(id="client-b", tenant_id="tenant-b", name="Beta Corp", code="BETA")
    db.add(client_b)
    wh_b = Warehouse(id="wh-b", tenant_id="tenant-b", name="WH-B", code="WHB")
    db.add(wh_b)
    sku_b = SKU(
        id="sku-gadget",
        tenant_id="tenant-b",
        client_id="client-b",
        sku_code="GADGET-001",
        name="Gadget",
    )
    db.add(sku_b)
    await db.flush()

    recv_b = ReceivingService(db, "tenant-b")
    order_b = await recv_b.create_inbound_order(
        client_id="client-b",
        warehouse_id="wh-b",
        order_number="PO-B-001",
        lines=[{"sku_id": "sku-gadget", "quantity": 30}],
    )

    # Verify orders belong to different tenants
    assert order_a.tenant_id == "tenant-a"
    assert order_b.tenant_id == "tenant-b"
    assert order_a.id != order_b.id


@pytest.mark.asyncio
async def test_receive_line_captures_measurements_and_note(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str, user_id: str
):
    fixtures = await setup_warehouse(db, tenant_id, client_id, warehouse_id)
    staging_id = fixtures["staging_id"]
    sku_id = fixtures["sku_id"]

    recv_svc = ReceivingService(db, tenant_id)
    order = await recv_svc.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="PO-2026-MEASURE-001",
        lines=[{"sku_id": sku_id, "quantity": 10}],
    )
    await recv_svc.start_receiving(order.id)

    from app.models.order import InboundOrderLine

    line_result = await db.execute(
        select(InboundOrderLine).where(InboundOrderLine.order_id == order.id)
    )
    line = line_result.scalar_one()

    receipt = await recv_svc.receive_line(
        order_id=order.id,
        line_id=line.id,
        quantity_received=10,
        quantity_damaged=1,
        staging_location_id=staging_id,
        measured_weight_kg=12.5,
        measured_length_cm=40,
        measured_width_cm=30,
        measured_height_cm=25,
        package_count=2,
        receiving_note="Outer carton slightly dented",
        user_id=user_id,
    )

    assert receipt["package_count"] == 2
    assert receipt["measured_weight_kg"] == 12.5
    assert receipt["measured_length_cm"] == 40.0
    assert receipt["receiving_note"] == "Outer carton slightly dented"

    refreshed = await db.get(InboundOrderLine, line.id)
    assert refreshed.package_count == 2
    assert float(refreshed.measured_weight_kg) == 12.5
    assert float(refreshed.measured_length_cm) == 40.0
    assert float(refreshed.measured_width_cm) == 30.0
    assert float(refreshed.measured_height_cm) == 25.0
    assert refreshed.receiving_note == "Outer carton slightly dented"


@pytest.mark.asyncio
async def test_receive_line_requires_staging_location_for_good_units(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str
):
    fixtures = await setup_warehouse(db, tenant_id, client_id, warehouse_id)
    sku_id = fixtures["sku_id"]

    recv_svc = ReceivingService(db, tenant_id)
    order = await recv_svc.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="PO-2026-STAGE-001",
        lines=[{"sku_id": sku_id, "quantity": 5}],
    )
    await recv_svc.start_receiving(order.id)

    from app.models.order import InboundOrderLine

    line_result = await db.execute(
        select(InboundOrderLine).where(InboundOrderLine.order_id == order.id)
    )
    line = line_result.scalar_one()

    with pytest.raises(HTTPException) as exc_info:
        await recv_svc.receive_line(
            order_id=order.id,
            line_id=line.id,
            quantity_received=5,
            quantity_damaged=0,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "staging_location_required"

    package = await db.scalar(
        select(InboundPackage).where(
            InboundPackage.tenant_id == tenant_id,
            InboundPackage.order_id == order.id,
            InboundPackage.order_line_id == line.id,
        )
    )
    label = await db.scalar(
        select(ReceivingLabel).where(
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id == order.id,
            ReceivingLabel.order_line_id == line.id,
        )
    )
    handling_unit = await db.scalar(
        select(HandlingUnit).where(
            HandlingUnit.tenant_id == tenant_id,
            HandlingUnit.order_id == order.id,
            HandlingUnit.order_line_id == line.id,
        )
    )
    assert package is None
    assert label is None
    assert handling_unit is None


@pytest.mark.asyncio
async def test_receive_line_damaged_only_skips_staging_inventory_and_putaway(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str, user_id: str
):
    fixtures = await setup_warehouse(db, tenant_id, client_id, warehouse_id)
    sku_id = fixtures["sku_id"]

    recv_svc = ReceivingService(db, tenant_id)
    order = await recv_svc.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="PO-2026-DAMAGED-001",
        lines=[{"sku_id": sku_id, "quantity": 5}],
    )
    await recv_svc.start_receiving(order.id)

    from app.models.order import InboundOrderLine

    line_result = await db.execute(
        select(InboundOrderLine).where(InboundOrderLine.order_id == order.id)
    )
    line = line_result.scalar_one()

    receipt = await recv_svc.receive_line(
        order_id=order.id,
        line_id=line.id,
        quantity_received=5,
        quantity_damaged=5,
        user_id=user_id,
    )

    assert receipt["status"] == "exact"
    assert receipt["label_status"] == "received"
    assert receipt["handling_unit_status"] == "received"

    package = await db.scalar(
        select(InboundPackage).where(
            InboundPackage.tenant_id == tenant_id,
            InboundPackage.order_id == order.id,
            InboundPackage.id == receipt["package_id"],
        )
    )
    handling_unit = await db.scalar(
        select(HandlingUnit).where(
            HandlingUnit.tenant_id == tenant_id,
            HandlingUnit.order_id == order.id,
            HandlingUnit.inbound_package_id == receipt["package_id"],
        )
    )
    inventory = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.sku_id == sku_id,
        )
    )

    assert package is not None
    assert package.status == InboundPackageStatus.RECEIVED.value
    assert handling_unit is not None
    assert handling_unit.received_qty == 0
    assert handling_unit.damaged_qty == 5
    assert handling_unit.staging_location_id is None
    assert inventory is None

    completion = await recv_svc.complete_receiving(order.id, user_id=user_id)
    assert completion["created_tasks"] == 0
    assert completion["putaway_units"] == 0

    task = await db.scalar(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    assert task is None


@pytest.mark.asyncio
async def test_receive_line_rejects_duplicate_default_package_confirmation(
    db: AsyncSession, tenant_id: str, client_id: str, warehouse_id: str, user_id: str
):
    fixtures = await setup_warehouse(db, tenant_id, client_id, warehouse_id)
    staging_id = fixtures["staging_id"]
    sku_id = fixtures["sku_id"]

    recv_svc = ReceivingService(db, tenant_id)
    order = await recv_svc.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="PO-2026-DUP-001",
        lines=[{"sku_id": sku_id, "quantity": 5}],
    )
    await recv_svc.start_receiving(order.id)

    from app.models.order import InboundOrderLine

    line_result = await db.execute(
        select(InboundOrderLine).where(InboundOrderLine.order_id == order.id)
    )
    line = line_result.scalar_one()

    await recv_svc.receive_line(
        order_id=order.id,
        line_id=line.id,
        quantity_received=5,
        quantity_damaged=0,
        staging_location_id=staging_id,
        user_id=user_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await recv_svc.receive_line(
            order_id=order.id,
            line_id=line.id,
            quantity_received=5,
            quantity_damaged=0,
            staging_location_id=staging_id,
            user_id=user_id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "line_already_received"
