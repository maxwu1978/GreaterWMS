from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import SKU
from app.models.order import (
    InboundOrder,
    InboundOrderLine,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
)
from app.models.task import Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.operations_board_service import OperationsBoardService


@pytest.mark.asyncio
async def test_operations_board_groups_work_and_avoids_pick_duplicates(db: AsyncSession) -> None:
    tenant_id = "board-tenant-1"
    client_id = "board-client-1"
    warehouse_id = "board-warehouse-1"
    now = datetime.now(UTC)

    db.add(
        Tenant(id=tenant_id, name="Board Tenant", code="BOARD1", contact_email="board@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Peak Client", code="PEAK"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Peak Demo", code="PEAK1"))
    db.add(
        Zone(
            id="board-zone-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Stage",
            code="STAGE",
        )
    )
    db.add(
        Location(
            id="board-location-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="board-zone-1",
            barcode="STAGE-01",
            aisle="S",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        Location(
            id="board-location-2",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="board-zone-1",
            barcode="A-01-01-01-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="board-sku-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="BOARD-SKU",
            name="Board SKU",
        )
    )

    db.add(
        InboundOrder(
            id="board-inbound-next",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="IN-NEXT",
            status=InboundStatus.EXPECTED.value,
            expected_date=now + timedelta(days=2),
        )
    )
    db.add(
        InboundOrder(
            id="board-inbound-now",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="IN-NOW",
            status=InboundStatus.RECEIVING.value,
            expected_date=now - timedelta(hours=2),
        )
    )
    db.add(
        InboundOrderLine(
            id="board-inbound-line",
            tenant_id=tenant_id,
            order_id="board-inbound-now",
            sku_id="board-sku-1",
            quantity_expected=8,
            quantity_received=2,
        )
    )
    db.add(
        OutboundOrder(
            id="board-outbound-next",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-NEXT",
            status=OutboundStatus.PENDING.value,
            required_ship_date=now + timedelta(days=2),
        )
    )
    db.add(
        OutboundOrder(
            id="board-outbound-now",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-NOW",
            status=OutboundStatus.PICKING.value,
            required_ship_date=now - timedelta(hours=2),
        )
    )
    db.add(
        OutboundOrderLine(
            id="board-outbound-line",
            tenant_id=tenant_id,
            order_id="board-outbound-now",
            sku_id="board-sku-1",
            quantity_ordered=4,
            quantity_picked=1,
        )
    )
    db.add(
        Task(
            id="board-putaway-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            quantity=8,
            source_location_id="board-location-1",
            destination_location_id="board-location-2",
            reference_type="inbound_order",
            reference_id="board-inbound-now",
        )
    )
    db.add(
        Task(
            id="board-pick-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PICK.value,
            status=TaskStatus.PENDING.value,
            quantity=4,
            reference_type="outbound_order",
            reference_id="board-outbound-now",
        )
    )
    db.add(
        Task(
            id="board-failed-task",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.MOVE.value,
            status=TaskStatus.FAILED.value,
            quantity=1,
            failure_reason="No available destination",
        )
    )
    await db.flush()

    board = await OperationsBoardService(db, tenant_id).build(warehouse_id=warehouse_id)
    items = {item["id"]: item for item in board["items"]}

    assert items["inbound:board-inbound-next"]["lane"] == "next"
    assert items["inbound:board-inbound-now"]["lane"] == "now"
    assert items["outbound:board-outbound-next"]["lane"] == "next"
    assert items["outbound:board-outbound-now"]["lane"] == "now"
    assert items["inbound:board-inbound-now"]["quantity"] == 8
    assert items["inbound:board-inbound-now"]["quantity_progress"] == 2
    assert items["task:board-putaway-task"]["location_label"] == "STAGE-01 -> A-01-01-01-01"
    assert items["task:board-failed-task"]["lane"] == "blocked"
    assert "task:board-pick-task" not in items
    assert board["counts"] == {
        "total": 6,
        "now": 3,
        "next": 2,
        "delayed": 0,
        "blocked": 1,
        "by_operation": {
            "receiving": 2,
            "putaway": 1,
            "picking": 2,
            "move": 1,
        },
    }


@pytest.mark.asyncio
async def test_operations_board_is_tenant_scoped(db: AsyncSession) -> None:
    db.add_all(
        [
            Tenant(
                id="board-tenant-a", name="Tenant A", code="BOARDA", contact_email="a@example.com"
            ),
            Tenant(
                id="board-tenant-b", name="Tenant B", code="BOARDB", contact_email="b@example.com"
            ),
            Client(id="board-client-a", tenant_id="board-tenant-a", name="Client A", code="A"),
            Client(id="board-client-b", tenant_id="board-tenant-b", name="Client B", code="B"),
            Warehouse(
                id="board-warehouse-a", tenant_id="board-tenant-a", name="Warehouse A", code="WA"
            ),
            Warehouse(
                id="board-warehouse-b", tenant_id="board-tenant-b", name="Warehouse B", code="WB"
            ),
            InboundOrder(
                id="board-inbound-a",
                tenant_id="board-tenant-a",
                client_id="board-client-a",
                warehouse_id="board-warehouse-a",
                order_number="IN-A",
                status=InboundStatus.EXPECTED.value,
            ),
            InboundOrder(
                id="board-inbound-b",
                tenant_id="board-tenant-b",
                client_id="board-client-b",
                warehouse_id="board-warehouse-b",
                order_number="IN-B",
                status=InboundStatus.EXPECTED.value,
            ),
        ]
    )
    await db.flush()

    board = await OperationsBoardService(db, "board-tenant-a").build()

    assert [item["reference_number"] for item in board["items"]] == ["IN-A"]
    assert board["counts"]["total"] == 1
