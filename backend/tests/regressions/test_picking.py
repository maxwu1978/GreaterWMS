"""Regression tests: picking (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.tasks import list_tasks
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.models.task import AssignedType, PickAllocation, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.picking_service import PickingService
from tests.regressions.helpers import setup_pick_fixture


@pytest.mark.asyncio
async def test_confirm_pick_rejects_zero_negative_and_excess_quantities(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """confirm_pick should reject invalid quantities without mutating inventory."""
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    svc = PickingService(db, tenant_id)

    zero_result = await svc.confirm_pick(fixtures["task_id"], 0, user_id)
    negative_result = await svc.confirm_pick(fixtures["task_id"], -5, user_id)
    excess_result = await svc.confirm_pick(fixtures["task_id"], 999, user_id)

    inv = (
        await db.execute(select(Inventory).where(Inventory.id == fixtures["inventory_id"]))
    ).scalar_one()

    assert zero_result["success"] is False
    assert zero_result["error_code"] == "pick_quantity_non_positive"
    assert zero_result["detail"]["error_code"] == "pick_quantity_non_positive"
    assert zero_result["detail"]["message"] == zero_result["error"]
    assert "greater than 0" in zero_result["error"]
    assert negative_result["success"] is False
    assert negative_result["error_code"] == "pick_quantity_non_positive"
    assert "greater than 0" in negative_result["error"]
    assert excess_result["success"] is False
    assert excess_result["error_code"] == "pick_quantity_exceeds_task"
    assert "exceeds task quantity" in excess_result["error"]
    assert inv.quantity_on_hand == 10
    assert inv.quantity_allocated == 5


@pytest.mark.asyncio
async def test_confirm_pick_rejects_repeat_confirmation(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """A completed pick task must not be confirmed a second time."""
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    svc = PickingService(db, tenant_id)

    first_result = await svc.confirm_pick(fixtures["task_id"], 5, user_id)
    second_result = await svc.confirm_pick(fixtures["task_id"], 5, user_id)

    inv = (
        await db.execute(select(Inventory).where(Inventory.id == fixtures["inventory_id"]))
    ).scalar_one()

    assert first_result["success"] is True
    assert second_result["success"] is False
    assert second_result["error_code"] == "pick_task_already_completed"
    assert second_result["error"] == "Task already completed"
    assert inv.quantity_on_hand == 5
    assert inv.quantity_allocated == 0


@pytest.mark.asyncio
async def test_assigned_pick_task_is_visible_and_confirmable_only_by_assigned_operator(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    fixtures = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    task = await db.get(Task, fixtures["task_id"])
    assert task is not None
    task.status = TaskStatus.ASSIGNED.value
    task.assigned_type = AssignedType.HUMAN.value
    task.assigned_to = user_id
    await db.flush()

    assigned_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.OPERATOR,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    other_user = TokenPayload(
        sub="operator-other",
        tenant_id=tenant_id,
        role=UserRole.OPERATOR,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    assigned_tasks = await list_tasks(
        warehouse_id=warehouse_id,
        status=TaskStatus.ASSIGNED.value,
        assigned_type=AssignedType.HUMAN.value,
        assigned_to=user_id,
        task_type=TaskType.PICK.value,
        limit=100,
        current_user=assigned_user,
        db=db,
    )
    other_tasks = await list_tasks(
        warehouse_id=warehouse_id,
        status=TaskStatus.ASSIGNED.value,
        assigned_type=AssignedType.HUMAN.value,
        assigned_to=None,
        task_type=TaskType.PICK.value,
        limit=100,
        current_user=other_user,
        db=db,
    )
    with pytest.raises(HTTPException) as forbidden:
        await list_tasks(
            warehouse_id=warehouse_id,
            status=TaskStatus.ASSIGNED.value,
            assigned_type=AssignedType.HUMAN.value,
            assigned_to=user_id,
            task_type=TaskType.PICK.value,
            limit=100,
            current_user=other_user,
            db=db,
        )

    svc = PickingService(db, tenant_id)
    rejected = await svc.confirm_pick(fixtures["task_id"], 2, "operator-other")
    accepted = await svc.confirm_pick(fixtures["task_id"], 2, user_id)
    inv = await db.get(Inventory, fixtures["inventory_id"])

    assert [task.id for task in assigned_tasks] == [fixtures["task_id"]]
    assert other_tasks == []
    assert forbidden.value.status_code == 403
    assert rejected["success"] is False
    assert rejected["error_code"] == "pick_task_assigned_to_other_operator"
    assert rejected["error"] == "Task is assigned to another operator"
    assert accepted["success"] is True
    assert inv is not None
    assert inv.quantity_on_hand == 8
    assert inv.quantity_allocated == 3


@pytest.mark.asyncio
async def test_pick_tasks_follow_split_allocations_across_locations(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Split Pick 3PL", code="SP3", contact_email="sp@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Split Client", code="SPC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Split Warehouse", code="SPW"))
    db.add(Zone(id="zone-split", tenant_id=tenant_id, warehouse_id=warehouse_id, name="A", code="A"))
    db.add_all(
        [
            Location(
                id="loc-split-a",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-split",
                barcode="A-01-01-01-01",
                aisle="01",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
                pick_sequence=1,
            ),
            Location(
                id="loc-split-b",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-split",
                barcode="A-01-02-01-01",
                aisle="01",
                rack="02",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
                pick_sequence=2,
            ),
        ]
    )
    db.add(
        SKU(
            id="sku-split",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-SPLIT",
            barcode="SKU-SPLIT-BAR",
            name="Split SKU",
        )
    )
    db.add_all(
        [
            Inventory(
                id="inv-split-a",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-split-a",
                sku_id="sku-split",
                quantity_on_hand=2,
                quantity_allocated=0,
                received_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            Inventory(
                id="inv-split-b",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-split-b",
                sku_id="sku-split",
                quantity_on_hand=4,
                quantity_allocated=0,
                received_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ]
    )
    db.add(
        OutboundOrder(
            id="order-split",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-SPLIT",
            status=OutboundStatus.PENDING.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="line-split",
            tenant_id=tenant_id,
            order_id="order-split",
            sku_id="sku-split",
            quantity_ordered=6,
        )
    )
    await db.flush()

    svc = PickingService(db, tenant_id)
    allocation = await svc.allocate_order("order-split")
    assert allocation["fully_allocated"] is True
    assert allocation["lines"][0]["pick_locations"] == [
        {"location_id": "loc-split-a", "quantity": 2, "lot_number": None},
        {"location_id": "loc-split-b", "quantity": 4, "lot_number": None},
    ]

    allocation_rows = (
        await db.execute(
            select(PickAllocation).where(PickAllocation.order_id == "order-split").order_by(
                PickAllocation.location_id
            )
        )
    ).scalars().all()
    assert [(row.location_id, row.quantity, row.quantity_picked) for row in allocation_rows] == [
        ("loc-split-a", 2, 0),
        ("loc-split-b", 4, 0),
    ]

    task_ids = await svc.create_pick_tasks("order-split")
    tasks = (
        await db.execute(
            select(Task).where(Task.id.in_(task_ids)).order_by(Task.source_location_id)
        )
    ).scalars().all()
    assert [(task.source_location_id, task.quantity) for task in tasks] == [
        ("loc-split-a", 2),
        ("loc-split-b", 4),
    ]
    assert {row.task_id for row in allocation_rows} == set(task_ids)

    first_pick = await svc.confirm_pick(tasks[0].id, 2, user_id)
    order = await db.get(OutboundOrder, "order-split")
    assert first_pick["success"] is True
    assert order is not None
    assert order.status == OutboundStatus.PICKING.value

    second_pick = await svc.confirm_pick(tasks[1].id, 4, user_id)
    line = await db.get(OutboundOrderLine, "line-split")
    inv_a = await db.get(Inventory, "inv-split-a")
    inv_b = await db.get(Inventory, "inv-split-b")
    assert second_pick["success"] is True
    assert order.status == OutboundStatus.PICKED.value
    assert line is not None
    assert line.quantity_picked == 6
    assert inv_a is not None and inv_a.quantity_on_hand == 0 and inv_a.quantity_allocated == 0
    assert inv_b is not None and inv_b.quantity_on_hand == 0 and inv_b.quantity_allocated == 0
