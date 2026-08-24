"""Regression tests: stage guards (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.orders import (
    OutboundReadinessRefreshRequest,
    list_outbound_orders,
    refresh_outbound_readiness,
)
from app.api.v1.endpoints.workbench_summaries import (
    inventory_summary,
    picking_summary,
    putaway_summary,
    receiving_summary,
)
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
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
    ReceivingLabel,
)
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.picking_service import PickingService
from app.services.putaway_service import PutawayService
from app.services.receiving_service import ReceivingService
from app.services.shipping_service import ShippingService


@pytest.mark.asyncio
async def test_scan_and_receive_label_guard_against_completed_or_duplicate_flow(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-rcv-2",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-3",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-FLOUR-20",
            name="Flour",
        )
    )
    db.add(
        Location(
            id="staging-2",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-rcv-2",
            barcode="STAGE-02",
            aisle="STAGE",
            rack="02",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-GUARD-001",
        lines=[{"sku_id": "sku-rcv-3", "quantity": 5}],
    )

    with pytest.raises(HTTPException) as scan_before_start:
        await service.scan_label(order.id, "RCV-ASN-GUARD-001-001")
    assert scan_before_start.value.status_code == 409

    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="RCV-ASN-GUARD-001-001",
        quantity_received=5,
        quantity_damaged=0,
        staging_location_id="staging-2",
        user_id=user_id,
    )

    with pytest.raises(HTTPException) as scan_twice:
        await service.scan_label(order.id, "RCV-ASN-GUARD-001-001")
    assert scan_twice.value.status_code == 409

    summary = await service.complete_receiving(order.id, user_id=user_id)
    assert summary["created_tasks"] == 1
    assert summary["putaway_units"] == 5


@pytest.mark.asyncio
async def test_workbench_summary_endpoints_return_aggregate_counts(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Summary 3PL", code="SUM", contact_email="sum@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Summary Client", code="SUMC"))
    db.add(
        Client(
            id="summary-other-client",
            tenant_id=tenant_id,
            name="Summary Other Client",
            code="SUMO",
        )
    )
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Summary Warehouse", code="SUMW"))
    db.add(
        Zone(
            id="summary-zone",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Summary Zone",
            code="SZ",
        )
    )
    db.add(
        Location(
            id="summary-loc",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="summary-zone",
            barcode="SUM-LOC-001",
            aisle="01",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
        )
    )
    db.add(
        SKU(
            id="summary-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SUM-SKU",
            name="Summary SKU",
        )
    )
    db.add(
        SKU(
            id="summary-other-sku",
            tenant_id=tenant_id,
            client_id="summary-other-client",
            sku_code="SUM-OTHER-SKU",
            name="Summary Other SKU",
        )
    )
    db.add(
        Inventory(
            id="summary-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="summary-loc",
            sku_id="summary-sku",
            quantity_on_hand=10,
            quantity_allocated=3,
            quantity_damaged=1,
        )
    )
    db.add(
        Inventory(
            id="summary-other-inv",
            tenant_id=tenant_id,
            client_id="summary-other-client",
            warehouse_id=warehouse_id,
            location_id="summary-loc",
            sku_id="summary-other-sku",
            quantity_on_hand=99,
        )
    )
    db.add(
        InboundOrder(
            id="summary-inbound",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="INB-SUM",
            status=InboundStatus.RECEIVING.value,
        )
    )
    db.add(
        InboundOrder(
            id="summary-inbound-complete",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="INB-SUM-C",
            status=InboundStatus.COMPLETED.value,
        )
    )
    db.add(
        InboundOrder(
            id="summary-other-inbound",
            tenant_id=tenant_id,
            client_id="summary-other-client",
            warehouse_id=warehouse_id,
            order_number="INB-SUM-OTHER",
            status=InboundStatus.RECEIVING.value,
        )
    )
    db.add(
        InboundOrderLine(
            id="summary-line",
            tenant_id=tenant_id,
            order_id="summary-inbound",
            sku_id="summary-sku",
            line_number=1,
            quantity_expected=6,
        )
    )
    db.add(
        InboundPackage(
            id="summary-package-open",
            tenant_id=tenant_id,
            order_id="summary-inbound",
            order_line_id="summary-line",
            package_number=1,
            status=InboundPackageStatus.STAGED.value,
            expected_qty=4,
        )
    )
    db.add(
        InboundPackage(
            id="summary-package-putaway",
            tenant_id=tenant_id,
            order_id="summary-inbound",
            order_line_id="summary-line",
            package_number=2,
            status=InboundPackageStatus.PUTAWAY_PENDING.value,
            expected_qty=2,
        )
    )
    db.add(
        ReceivingLabel(
            id="summary-label",
            tenant_id=tenant_id,
            order_id="summary-inbound",
            order_line_id="summary-line",
            sku_id="summary-sku",
            label_code="RCV-SUM-001",
            expected_qty=4,
            status="received",
            extra_data={"print_count": 0},
        )
    )
    db.add(
        OutboundOrder(
            id="summary-outbound",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-SUM",
            status=OutboundStatus.PICKING.value,
        )
    )
    db.add(
        OutboundOrder(
            id="summary-other-outbound",
            tenant_id=tenant_id,
            client_id="summary-other-client",
            warehouse_id=warehouse_id,
            order_number="OUT-SUM-OTHER",
            status=OutboundStatus.PICKING.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="summary-outbound-line",
            tenant_id=tenant_id,
            order_id="summary-outbound",
            sku_id="summary-sku",
            quantity_ordered=6,
            quantity_allocated=5,
            quantity_picked=2,
        )
    )
    db.add(
        Task(
            id="summary-putaway-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            sku_id="summary-sku",
            quantity=4,
            source_location_id="summary-loc",
            assigned_type=AssignedType.UNASSIGNED.value,
            reference_type="inbound_order",
            reference_id="summary-inbound",
        )
    )
    db.add(
        Task(
            id="summary-pick-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PICK.value,
            status=TaskStatus.ASSIGNED.value,
            priority=5,
            sku_id="summary-sku",
            quantity=2,
            source_location_id="summary-loc",
            assigned_type=AssignedType.HUMAN.value,
            reference_type="outbound_order",
            reference_id="summary-outbound",
        )
    )
    db.add(
        Task(
            id="summary-other-putaway-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            sku_id="summary-other-sku",
            quantity=99,
            source_location_id="summary-loc",
            assigned_type=AssignedType.UNASSIGNED.value,
            reference_type="inbound_order",
            reference_id="summary-other-inbound",
        )
    )
    db.add(
        Task(
            id="summary-other-pick-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PICK.value,
            status=TaskStatus.ASSIGNED.value,
            priority=5,
            sku_id="summary-other-sku",
            quantity=99,
            source_location_id="summary-loc",
            assigned_type=AssignedType.HUMAN.value,
            reference_type="outbound_order",
            reference_id="summary-other-outbound",
        )
    )
    await db.flush()

    user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    receiving = await receiving_summary(
        warehouse_id=warehouse_id,
        client_id=client_id,
        current_user=user,
        db=db,
    )
    putaway = await putaway_summary(
        warehouse_id=warehouse_id,
        client_id=client_id,
        current_user=user,
        db=db,
    )
    picking = await picking_summary(
        warehouse_id=warehouse_id,
        client_id=client_id,
        current_user=user,
        db=db,
    )
    inventory = await inventory_summary(
        warehouse_id=warehouse_id,
        client_id=client_id,
        current_user=user,
        db=db,
    )

    assert receiving.total_orders == 2
    assert receiving.completed_orders == 1
    assert receiving.packages_open == 1
    assert receiving.packages_putaway_pending == 1
    assert receiving.internal_labels_print_pending == 1
    assert putaway.pending_tasks == 1
    assert putaway.pending_units == 4
    assert putaway.by_assigned_type[AssignedType.UNASSIGNED.value] == 1
    assert picking.by_status[OutboundStatus.PICKING.value] == 1
    assert picking.total_ordered_units == 6
    assert picking.total_allocated_units == 5
    assert picking.total_picked_units == 2
    assert picking.active_pick_tasks == 1
    assert inventory.inventory_rows == 1
    assert inventory.on_hand_units == 10
    assert inventory.allocated_units == 3
    assert inventory.damaged_units == 1
    assert inventory.available_units == 6


@pytest.mark.asyncio
async def test_receiving_stage_guards_reject_wrong_order_status(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Stage Guard 3PL", code="SG3", contact_email="sg@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Stage Client", code="SGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Stage Warehouse", code="SGW"))
    db.add(
        SKU(
            id="sku-stage-receiving",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-STAGE-RCV",
            name="Receiving Stage SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="INB-STAGE-OPEN",
        lines=[{"sku_id": "sku-stage-receiving", "quantity": 3}],
    )

    opened = await service.start_receiving(order.id)
    opened_again = await service.start_receiving(order.id)

    assert opened.status == InboundStatus.RECEIVING.value
    assert opened_again.status == InboundStatus.RECEIVING.value

    not_started = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="INB-STAGE-NOT-STARTED",
        lines=[{"sku_id": "sku-stage-receiving", "quantity": 1}],
    )
    with pytest.raises(HTTPException) as early_complete:
        await service.complete_receiving(not_started.id)
    assert early_complete.value.status_code == 409

    blocked_statuses = [
        InboundStatus.DRAFT,
        InboundStatus.PUTAWAY,
        InboundStatus.COMPLETED,
        InboundStatus.CANCELLED,
    ]
    for index, blocked_status in enumerate(blocked_statuses, start=1):
        db.add(
            InboundOrder(
                id=f"inb-stage-blocked-{index}",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number=f"INB-STAGE-BLOCKED-{index}",
                status=blocked_status.value,
            )
        )
    await db.flush()

    for index, blocked_status in enumerate(blocked_statuses, start=1):
        with pytest.raises(HTTPException) as blocked_start:
            await service.start_receiving(f"inb-stage-blocked-{index}")
        assert blocked_start.value.status_code == 409
        assert blocked_status.value in str(blocked_start.value.detail)


@pytest.mark.asyncio
async def test_outbound_stage_guards_enforce_picking_and_shipping_order(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Outbound Guard 3PL", code="OG3", contact_email="og@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Outbound Client", code="OGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Outbound Warehouse", code="OGW"))
    db.add(
        Zone(
            id="zone-outbound-stage",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Pick Zone",
            code="PICK",
        )
    )
    db.add(
        Location(
            id="loc-outbound-stage",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-outbound-stage",
            barcode="A-01-01-01-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id="sku-outbound-stage",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-STAGE-OUT",
            name="Outbound Stage SKU",
        )
    )
    db.add(
        Inventory(
            id="inv-outbound-stage",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-outbound-stage",
            sku_id="sku-outbound-stage",
            quantity_on_hand=20,
            quantity_allocated=0,
        )
    )
    db.add(
        OutboundOrder(
            id="out-stage-main",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-STAGE-MAIN",
            status=OutboundStatus.PENDING.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="out-stage-main-line",
            tenant_id=tenant_id,
            order_id="out-stage-main",
            sku_id="sku-outbound-stage",
            quantity_ordered=4,
        )
    )
    await db.flush()

    pick_service = PickingService(db, tenant_id)
    allocation = await pick_service.allocate_order("out-stage-main")
    main_order = await db.get(OutboundOrder, "out-stage-main")

    assert allocation["fully_allocated"] is True
    assert main_order is not None
    assert main_order.status == OutboundStatus.ALLOCATED.value

    with pytest.raises(HTTPException) as repeated_allocate:
        await pick_service.allocate_order("out-stage-main")
    assert repeated_allocate.value.status_code == 409
    assert repeated_allocate.value.detail["error_code"] == "pick_allocate_order_not_pending"

    task_ids = await pick_service.create_pick_tasks("out-stage-main")
    assert len(task_ids) == 1
    assert main_order.status == OutboundStatus.PICKING.value

    with pytest.raises(HTTPException) as repeated_release:
        await pick_service.create_pick_tasks("out-stage-main")
    assert repeated_release.value.status_code == 409
    assert repeated_release.value.detail["error_code"] == "pick_release_order_not_allocated"

    db.add(
        OutboundOrder(
            id="out-stage-pending",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-STAGE-PENDING",
            status=OutboundStatus.PENDING.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="out-stage-pending-line",
            tenant_id=tenant_id,
            order_id="out-stage-pending",
            sku_id="sku-outbound-stage",
            quantity_ordered=1,
        )
    )
    await db.flush()

    with pytest.raises(HTTPException) as premature_pick_release:
        await pick_service.create_pick_tasks("out-stage-pending")
    assert premature_pick_release.value.status_code == 409
    assert premature_pick_release.value.detail["error_code"] == "pick_release_order_not_allocated"

    pick_result = await pick_service.confirm_pick(task_ids[0], 4, user_id)
    assert pick_result["success"] is True
    assert main_order.status == OutboundStatus.PICKED.value

    shipping_service = ShippingService(db, tenant_id)
    pack_result = await shipping_service.verify_pack(
        "out-stage-main",
        [{"sku_id": "sku-outbound-stage", "quantity": 4}],
        user_id,
    )
    assert pack_result["verified"] is True
    assert main_order.status == OutboundStatus.PACKED.value

    ship_result = await shipping_service.ship_confirm(
        "out-stage-main",
        carrier="UPS",
        tracking_number="1ZSTAGE",
        user_id=user_id,
    )
    assert ship_result["status"] == "shipped"
    assert main_order.status == OutboundStatus.SHIPPED.value

    with pytest.raises(HTTPException) as pack_before_pick:
        await shipping_service.verify_pack(
            "out-stage-pending",
            [{"sku_id": "sku-outbound-stage", "quantity": 1}],
            user_id,
        )
    assert pack_before_pick.value.status_code == 409

    db.add(
        OutboundOrder(
            id="out-stage-picked-not-packed",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-STAGE-PICKED-NOT-PACKED",
            status=OutboundStatus.PICKED.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="out-stage-picked-not-packed-line",
            tenant_id=tenant_id,
            order_id="out-stage-picked-not-packed",
            sku_id="sku-outbound-stage",
            quantity_ordered=1,
            quantity_picked=1,
        )
    )
    await db.flush()

    with pytest.raises(HTTPException) as ship_before_pack:
        await shipping_service.ship_confirm(
            "out-stage-picked-not-packed",
            carrier="UPS",
            tracking_number="1ZEARLY",
            user_id=user_id,
        )
    assert ship_before_pack.value.status_code == 409


@pytest.mark.asyncio
async def test_outbound_list_includes_pick_readiness_summary(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Pick Readiness 3PL", code="PR3", contact_email="pr@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Pick Readiness Client", code="PRC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Pick Warehouse", code="PWH"))
    db.add(
        Zone(
            id="zone-pick-readiness",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Pick Readiness Zone",
            code="PR",
        )
    )
    db.add(
        Location(
            id="loc-pick-readiness",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-pick-readiness",
            barcode="PR-01-01-01-01",
            aisle="PR",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add_all(
        [
            SKU(
                id="sku-pick-ready",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="SKU-PICK-READY",
                name="Pick Ready SKU",
            ),
            SKU(
                id="sku-pick-short",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="SKU-PICK-SHORT",
                name="Pick Short SKU",
            ),
        ]
    )
    db.add_all(
        [
            Inventory(
                id="inv-pick-ready",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-pick-readiness",
                sku_id="sku-pick-ready",
                quantity_on_hand=10,
                quantity_allocated=0,
                quantity_damaged=0,
            ),
            Inventory(
                id="inv-pick-short",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-pick-readiness",
                sku_id="sku-pick-short",
                quantity_on_hand=1,
                quantity_allocated=0,
                quantity_damaged=0,
            ),
        ]
    )
    db.add_all(
        [
            OutboundOrder(
                id="out-pick-ready",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number="OUT-PICK-READY",
                status=OutboundStatus.PENDING.value,
            ),
            OutboundOrder(
                id="out-pick-short",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number="OUT-PICK-SHORT",
                status=OutboundStatus.PENDING.value,
            ),
            OutboundOrder(
                id="out-pick-release",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                order_number="OUT-PICK-RELEASE",
                status=OutboundStatus.ALLOCATED.value,
            ),
        ]
    )
    db.add_all(
        [
            OutboundOrderLine(
                id="out-pick-ready-line",
                tenant_id=tenant_id,
                order_id="out-pick-ready",
                sku_id="sku-pick-ready",
                quantity_ordered=3,
            ),
            OutboundOrderLine(
                id="out-pick-short-line",
                tenant_id=tenant_id,
                order_id="out-pick-short",
                sku_id="sku-pick-short",
                quantity_ordered=5,
            ),
            OutboundOrderLine(
                id="out-pick-release-line",
                tenant_id=tenant_id,
                order_id="out-pick-release",
                sku_id="sku-pick-ready",
                quantity_ordered=2,
                quantity_allocated=2,
            ),
        ]
    )
    await db.flush()

    current_user = TokenPayload(
        sub="pick-readiness-user",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    rows = await list_outbound_orders(
        response=Response(),
        warehouse_id=None,
        status=None,
        current_user=current_user,
        db=db,
    )
    by_order_number = {row.order_number: row for row in rows}

    assert by_order_number["OUT-PICK-READY"].pick_readiness == "ready_to_allocate"
    assert by_order_number["OUT-PICK-READY"].pick_shortage_units == 0
    assert by_order_number["OUT-PICK-READY"].total_items == 3

    assert by_order_number["OUT-PICK-SHORT"].pick_readiness == "short_stock"
    assert by_order_number["OUT-PICK-SHORT"].pick_shortage_units == 4
    assert by_order_number["OUT-PICK-SHORT"].total_allocated == 0

    assert by_order_number["OUT-PICK-RELEASE"].pick_readiness == "ready_to_release"
    assert by_order_number["OUT-PICK-RELEASE"].pick_shortage_units == 0
    assert by_order_number["OUT-PICK-RELEASE"].total_allocated == 2

    stored_orders = await db.execute(
        select(OutboundOrder).where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.order_number.in_(
                ["OUT-PICK-READY", "OUT-PICK-SHORT", "OUT-PICK-RELEASE"]
            ),
        )
    )
    rank_by_order_number = {
        order.order_number: order.pick_readiness_rank for order in stored_orders.scalars()
    }
    assert rank_by_order_number == {
        "OUT-PICK-READY": 20,
        "OUT-PICK-SHORT": 10,
        "OUT-PICK-RELEASE": 30,
    }


@pytest.mark.asyncio
async def test_outbound_readiness_refresh_updates_stale_pending_rank(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Refresh 3PL", code="RFR", contact_email="rfr@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Refresh Client", code="RFC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Refresh Warehouse", code="RWH"))
    db.add(
        Zone(
            id="zone-readiness-refresh",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Refresh Zone",
            code="RF",
        )
    )
    db.add(
        Location(
            id="loc-readiness-refresh",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-readiness-refresh",
            barcode="RF-01",
            aisle="RF",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.OCCUPIED.value,
        )
    )
    db.add(
        SKU(
            id="sku-readiness-refresh",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-RFR",
            name="Refresh SKU",
        )
    )
    db.add(
        Inventory(
            id="inv-readiness-refresh",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-readiness-refresh",
            sku_id="sku-readiness-refresh",
            quantity_on_hand=0,
            quantity_allocated=0,
            quantity_damaged=0,
        )
    )
    db.add(
        OutboundOrder(
            id="out-readiness-refresh",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-RFR-001",
            status=OutboundStatus.PENDING.value,
            pick_readiness_rank=20,
        )
    )
    db.add(
        OutboundOrderLine(
            id="out-readiness-refresh-line",
            tenant_id=tenant_id,
            order_id="out-readiness-refresh",
            sku_id="sku-readiness-refresh",
            quantity_ordered=5,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="readiness-refresh-user",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    dry_run = await refresh_outbound_readiness(
        OutboundReadinessRefreshRequest(order_id="out-readiness-refresh", dry_run=True),
        current_user=current_user,
        db=db,
    )
    assert dry_run.scanned_orders == 1
    assert dry_run.updated_orders == 1
    assert dry_run.changes[0].old_pick_rank == 20
    assert dry_run.changes[0].new_pick_rank == 10

    order = await db.get(OutboundOrder, "out-readiness-refresh")
    assert order.pick_readiness_rank == 20

    applied = await refresh_outbound_readiness(
        OutboundReadinessRefreshRequest(order_id="out-readiness-refresh", dry_run=False),
        current_user=current_user,
        db=db,
    )
    assert applied.updated_orders == 1
    assert order.pick_readiness_rank == 10

    inventory = await db.get(Inventory, "inv-readiness-refresh")
    inventory.quantity_on_hand = 10
    await db.flush()

    restocked = await refresh_outbound_readiness(
        OutboundReadinessRefreshRequest(order_id="out-readiness-refresh", dry_run=False),
        current_user=current_user,
        db=db,
    )
    assert restocked.updated_orders == 1
    assert restocked.changes[0].old_pick_rank == 10
    assert restocked.changes[0].new_pick_rank == 20
    assert order.pick_readiness_rank == 20


@pytest.mark.asyncio
async def test_verify_pack_rejects_missing_picked_sku(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Pack Completeness 3PL",
            code="PC3",
            contact_email="pc@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Pack Client", code="PCC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Pack Warehouse", code="PCW"))
    db.add(
        OutboundOrder(
            id="out-pack-complete",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-PACK-COMPLETE",
            status=OutboundStatus.PICKED.value,
        )
    )
    db.add_all(
        [
            SKU(
                id="sku-pack-a",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="SKU-PACK-A",
                name="Pack SKU A",
            ),
            SKU(
                id="sku-pack-b",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="SKU-PACK-B",
                name="Pack SKU B",
            ),
            OutboundOrderLine(
                id="out-pack-complete-line-a",
                tenant_id=tenant_id,
                order_id="out-pack-complete",
                sku_id="sku-pack-a",
                quantity_ordered=2,
                quantity_picked=2,
            ),
            OutboundOrderLine(
                id="out-pack-complete-line-b",
                tenant_id=tenant_id,
                order_id="out-pack-complete",
                sku_id="sku-pack-b",
                quantity_ordered=3,
                quantity_picked=3,
            ),
        ]
    )
    await db.flush()

    service = ShippingService(db, tenant_id)

    partial_result = await service.verify_pack(
        "out-pack-complete",
        [{"sku_id": "sku-pack-a", "quantity": 2}],
        user_id,
    )

    assert partial_result["verified"] is False
    assert {
        "sku_id": "sku-pack-b",
        "error": "quantity_mismatch",
        "expected": 3,
        "scanned": 0,
    } in partial_result["errors"]
    order = await db.get(OutboundOrder, "out-pack-complete")
    assert order is not None
    assert order.status == OutboundStatus.PICKED.value

    complete_result = await service.verify_pack(
        "out-pack-complete",
        [
            {"sku_id": "sku-pack-a", "quantity": 1},
            {"sku_id": "sku-pack-a", "quantity": 1},
            {"sku_id": "sku-pack-b", "quantity": 3},
        ],
        user_id,
    )

    assert complete_result["verified"] is True
    assert complete_result["errors"] == []
    assert order.status == OutboundStatus.PACKED.value


@pytest.mark.asyncio
async def test_putaway_rejects_tasks_before_inbound_order_is_released(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Putaway Guard 3PL", code="PG3", contact_email="pg@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Putaway Client", code="PGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Putaway Warehouse", code="PGW"))
    db.add(
        Zone(
            id="zone-putaway-stage",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Putaway Zone",
            code="PUT",
        )
    )
    db.add(
        Location(
            id="loc-putaway-source",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-putaway-stage",
            barcode="STAGE-01",
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
            id="loc-putaway-destination",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-putaway-stage",
            barcode="A-02-01-01-01",
            aisle="A",
            rack="02",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-putaway-stage",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-STAGE-PUT",
            name="Putaway Stage SKU",
        )
    )
    db.add(
        InboundOrder(
            id="inb-putaway-not-released",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="INB-PUTAWAY-NOT-RELEASED",
            status=InboundStatus.RECEIVING.value,
        )
    )
    db.add(
        InboundOrderLine(
            id="inb-putaway-line",
            tenant_id=tenant_id,
            order_id="inb-putaway-not-released",
            sku_id="sku-putaway-stage",
            line_number=1,
            quantity_expected=3,
            quantity_received=3,
            staging_location_id="loc-putaway-source",
        )
    )
    db.add(
        Inventory(
            id="inv-putaway-source",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-putaway-source",
            sku_id="sku-putaway-stage",
            quantity_on_hand=3,
        )
    )
    db.add(
        Task(
            id="task-putaway-not-released",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-stage",
            quantity=3,
            source_location_id="loc-putaway-source",
            reference_type="inbound_order",
            reference_id="inb-putaway-not-released",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()

    result = await PutawayService(db, tenant_id).confirm_putaway(
        "task-putaway-not-released",
        "loc-putaway-destination",
        user_id=user_id,
    )
    source_inventory = await db.get(Inventory, "inv-putaway-source")
    task = await db.get(Task, "task-putaway-not-released")

    assert result["success"] is False
    assert result["error_code"] == "putaway_inbound_not_released"
    assert "released to putaway" in result["error"]
    assert source_inventory is not None
    assert source_inventory.quantity_on_hand == 3
    assert task is not None
    assert task.status == TaskStatus.PENDING.value
