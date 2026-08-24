"""Regression tests: putaway (split from tests/test_regressions.py)."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.tasks import (
    PutawayTaskRepairRequest,
    list_tasks,
    repair_putaway_task_records,
)
from app.core.security import TokenPayload, UserRole
from app.models.agent_evidence import AgentEvidence
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
)
from app.models.task import AssignedType, PutawayAllocation, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.putaway_service import PutawayService
from app.services.receiving_service import ReceivingService


@pytest.mark.asyncio
async def test_complete_receiving_creates_putaway_task_with_handling_unit(
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
            id="zone-hu-task-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-hu-task-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-003",
            name="HU Item 3",
        )
    )
    db.add(
        Location(
            id="staging-hu-task-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-hu-task-1",
            barcode="STAGE-HU-TASK-01",
            aisle="STAGE",
            rack="01",
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
        order_number="ASN-HU-TASK-001",
        lines=[{"sku_id": "sku-hu-task-1", "quantity": 6}],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="RCV-ASN-HU-TASK-001-001",
        quantity_received=6,
        quantity_damaged=1,
        staging_location_id="staging-hu-task-1",
        user_id=user_id,
    )

    await service.complete_receiving(order.id, user_id=user_id)

    handling_unit = await db.scalar(select(HandlingUnit).where(HandlingUnit.order_id == order.id))
    task = await db.scalar(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )

    assert handling_unit is not None
    assert task is not None
    assert task.handling_unit_id == handling_unit.id
    assert task.execution_mode == AssignedType.HUMAN.value
    assert task.quantity == 5


@pytest.mark.asyncio
async def test_complete_receiving_rejects_received_units_without_staging(
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
        SKU(
            id="sku-hu-missing-source",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-MISSING",
            name="HU Missing Source",
        )
    )
    order = InboundOrder(
        id="order-hu-missing-source",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-HU-MISSING-SOURCE",
        status=InboundStatus.RECEIVING.value,
    )
    line = InboundOrderLine(
        id="line-hu-missing-source",
        tenant_id=tenant_id,
        order_id=order.id,
        sku_id="sku-hu-missing-source",
        line_number=1,
        quantity_expected=5,
        quantity_received=5,
    )
    package = InboundPackage(
        id="pkg-hu-missing-source",
        tenant_id=tenant_id,
        order_id=order.id,
        order_line_id=line.id,
        package_number=1,
        package_type="carton",
        status=InboundPackageStatus.RECEIVED.value,
        expected_qty=5,
        received_qty=5,
        damaged_qty=0,
    )
    handling_unit = HandlingUnit(
        id="hu-missing-source",
        tenant_id=tenant_id,
        order_id=order.id,
        order_line_id=line.id,
        inbound_package_id=package.id,
        sku_id="sku-hu-missing-source",
        unit_code="RCV-HU-MISSING-SOURCE-001",
        expected_qty=5,
        received_qty=5,
        damaged_qty=0,
        status="received",
        staging_location_id=None,
    )
    db.add_all([order, line, package, handling_unit])
    await db.flush()

    service = ReceivingService(db, tenant_id)
    with pytest.raises(HTTPException) as exc_info:
        await service.complete_receiving(order.id, user_id=user_id)

    task_ids = (
        (await db.execute(select(Task.id).where(Task.reference_id == order.id))).scalars().all()
    )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "staging_location_required"
    assert order.status == InboundStatus.RECEIVING.value
    assert task_ids == []


@pytest.mark.asyncio
async def test_complete_receiving_rejects_open_expected_packages(
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
            id="zone-open-package",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-open-package",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-open-package",
            barcode="STAGE-OPEN-PACKAGE",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-open-package",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OPEN-PACKAGE",
            name="Open Package Guard",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-OPEN-PACKAGE",
        lines=[
            {
                "sku_id": "sku-open-package",
                "quantity": 8,
                "packages": [
                    {
                        "package_number": 1,
                        "expected_qty": 4,
                        "external_tracking_number": "OPEN-PKG-1",
                    },
                    {
                        "package_number": 2,
                        "expected_qty": 4,
                        "external_tracking_number": "OPEN-PKG-2",
                    },
                ],
            }
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="OPEN-PKG-1",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-open-package",
        user_id=user_id,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.complete_receiving(order.id, user_id=user_id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "open_packages_remain"
    assert "package 2" in exc_info.value.detail["message"]
    assert order.status == InboundStatus.RECEIVING.value


@pytest.mark.asyncio
async def test_complete_receiving_recovers_putaway_source_from_package_staging(
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
            id="zone-hu-recover-source",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-hu-recover-source",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-hu-recover-source",
            barcode="STAGE-HU-RECOVER-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-hu-recover-source",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-RECOVER",
            name="HU Recover Source",
        )
    )
    order = InboundOrder(
        id="order-hu-recover-source",
        tenant_id=tenant_id,
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-HU-RECOVER-SOURCE",
        status=InboundStatus.RECEIVING.value,
    )
    line = InboundOrderLine(
        id="line-hu-recover-source",
        tenant_id=tenant_id,
        order_id=order.id,
        sku_id="sku-hu-recover-source",
        line_number=1,
        quantity_expected=5,
        quantity_received=5,
    )
    package = InboundPackage(
        id="pkg-hu-recover-source",
        tenant_id=tenant_id,
        order_id=order.id,
        order_line_id=line.id,
        package_number=1,
        package_type="carton",
        status=InboundPackageStatus.STAGED.value,
        expected_qty=5,
        received_qty=5,
        damaged_qty=0,
        staging_location_id="staging-hu-recover-source",
    )
    handling_unit = HandlingUnit(
        id="hu-recover-source",
        tenant_id=tenant_id,
        order_id=order.id,
        order_line_id=line.id,
        inbound_package_id=package.id,
        sku_id="sku-hu-recover-source",
        unit_code="RCV-HU-RECOVER-SOURCE-001",
        expected_qty=5,
        received_qty=5,
        damaged_qty=0,
        status="received",
        staging_location_id=None,
    )
    db.add_all([order, line, package, handling_unit])
    await db.flush()

    service = ReceivingService(db, tenant_id)
    await service.complete_receiving(order.id, user_id=user_id)

    task = await db.scalar(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )

    assert handling_unit.staging_location_id == "staging-hu-recover-source"
    assert task is not None
    assert task.source_location_id == "staging-hu-recover-source"


@pytest.mark.asyncio
async def test_confirm_putaway_supports_split_allocations(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Split Tenant", code="SPL", contact_email="split@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-split",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-split",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SPLIT-001",
            name="Split SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-split",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split",
                barcode="STAGE-SPLIT-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-split-a",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split",
                barcode="A-01-01-01-01",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-split-b",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split",
                barcode="A-01-01-01-02",
                aisle="A",
                rack="01",
                level="01",
                position="02",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        Inventory(
            id="inv-stage-split",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-stage-split",
            sku_id="sku-putaway-split",
            quantity_on_hand=5,
        )
    )
    db.add(
        Task(
            id="task-putaway-split",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-split",
            quantity=5,
            source_location_id="loc-stage-split",
            reference_type="inbound_order",
            reference_id="order-putaway-split",
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    result = await service.confirm_putaway(
        "task-putaway-split",
        "loc-dest-split-a",
        user_id,
        allocations=[
            {"location_id": "loc-dest-split-a", "quantity": 3},
            {"location_id": "loc-dest-split-b", "quantity": 2},
        ],
    )

    source_inventory = (
        await db.execute(select(Inventory).where(Inventory.id == "inv-stage-split"))
    ).scalar_one()
    dest_a = (
        await db.execute(
            select(Inventory).where(
                Inventory.location_id == "loc-dest-split-a",
                Inventory.sku_id == "sku-putaway-split",
            )
        )
    ).scalar_one()
    dest_b = (
        await db.execute(
            select(Inventory).where(
                Inventory.location_id == "loc-dest-split-b",
                Inventory.sku_id == "sku-putaway-split",
            )
        )
    ).scalar_one()
    allocations = (
        (
            await db.execute(
                select(PutawayAllocation).where(PutawayAllocation.task_id == "task-putaway-split")
            )
        )
        .scalars()
        .all()
    )

    assert result["success"] is True
    assert len(result["allocations"]) == 2
    assert source_inventory.quantity_on_hand == 0
    assert dest_a.quantity_on_hand == 3
    assert dest_b.quantity_on_hand == 2
    assert len(allocations) == 2


@pytest.mark.asyncio
async def test_putaway_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Putaway Evidence Tenant",
            code="PET",
            contact_email="putaway-evidence@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Putaway Client", code="PWC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Putaway Warehouse", code="PWH"))
    db.add(
        Zone(
            id="zone-putaway-evidence",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Evidence Zone",
            code="PEZ",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-evidence",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="PWE-001",
            name="Putaway Evidence SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-evidence",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-evidence",
                barcode="STAGE-EVIDENCE",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-evidence",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-evidence",
                barcode="DEST-EVIDENCE",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        Inventory(
            id="inv-stage-evidence",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-stage-evidence",
            sku_id="sku-putaway-evidence",
            quantity_on_hand=4,
        )
    )
    db.add(
        Task(
            id="task-putaway-evidence",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-evidence",
            quantity=4,
            source_location_id="loc-stage-evidence",
            reference_type="inbound_order",
            reference_id="order-putaway-evidence",
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    preview = await service.preview_putaway_confirmation(
        task_id="task-putaway-evidence",
        destination_location_id="loc-dest-evidence",
        user_id=user_id,
    )

    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["confirmation_payload"]["confirmation_token"].startswith("put-confirm:")
    assert preview["confirmation_payload"]["evidence_id"] == preview["evidence_id"]

    task = await db.scalar(select(Task).where(Task.id == "task-putaway-evidence"))
    source_inventory = await db.scalar(select(Inventory).where(Inventory.id == "inv-stage-evidence"))
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    allocations = (
        await db.execute(
            select(PutawayAllocation).where(PutawayAllocation.task_id == "task-putaway-evidence")
        )
    ).scalars().all()
    assert task is not None
    assert source_inventory is not None
    assert evidence is not None
    assert task.status == TaskStatus.PENDING.value
    assert source_inventory.quantity_on_hand == 4
    assert allocations == []
    assert evidence.status == "previewed"

    confirmed = await service.confirm_putaway_with_token(
        task_id="task-putaway-evidence",
        destination_location_id="loc-dest-evidence",
        confirmation_token=preview["confirmation_payload"]["confirmation_token"],
        user_id=user_id,
        idempotency_key="putaway-agent-confirm-test",
    )

    assert confirmed["ok"] is True
    assert confirmed["dry_run"] is False
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "putaway-agent-confirm-test"

    task = await db.scalar(select(Task).where(Task.id == "task-putaway-evidence"))
    source_inventory = await db.scalar(select(Inventory).where(Inventory.id == "inv-stage-evidence"))
    dest_inventory = await db.scalar(
        select(Inventory).where(
            Inventory.location_id == "loc-dest-evidence",
            Inventory.sku_id == "sku-putaway-evidence",
        )
    )
    assert task is not None
    assert source_inventory is not None
    assert dest_inventory is not None
    assert task.status == TaskStatus.COMPLETED.value
    assert source_inventory.quantity_on_hand == 0
    assert dest_inventory.quantity_on_hand == 4


@pytest.mark.asyncio
async def test_confirm_putaway_blocks_different_sku_destination_by_default(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id, name="Putaway Policy Tenant", code="PPT", contact_email="ops@example.com"
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-policy",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add_all(
        [
            SKU(
                id="sku-putaway-policy-a",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="DAN-POL-A",
                name="Policy A",
            ),
            SKU(
                id="sku-putaway-policy-b",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="DAN-POL-B",
                name="Policy B",
            ),
            Location(
                id="loc-stage-policy",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-policy",
                barcode="STAGE-POLICY-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-policy",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-policy",
                barcode="A-01-01-01-01",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
            ),
        ]
    )
    db.add_all(
        [
            Inventory(
                id="inv-stage-policy",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-stage-policy",
                sku_id="sku-putaway-policy-a",
                quantity_on_hand=4,
            ),
            Inventory(
                id="inv-dest-policy",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-dest-policy",
                sku_id="sku-putaway-policy-b",
                quantity_on_hand=2,
            ),
            Task(
                id="task-putaway-policy",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                sku_id="sku-putaway-policy-a",
                quantity=4,
                source_location_id="loc-stage-policy",
                reference_type="inbound_order",
                reference_id="order-putaway-policy",
            ),
        ]
    )
    await db.flush()

    result = await PutawayService(db, tenant_id).confirm_putaway(
        "task-putaway-policy",
        "loc-dest-policy",
        user_id,
    )

    source_inventory = await db.scalar(select(Inventory).where(Inventory.id == "inv-stage-policy"))
    task = await db.scalar(select(Task).where(Task.id == "task-putaway-policy"))

    assert result["success"] is False
    assert "different SKU" in result["error"]
    assert source_inventory.quantity_on_hand == 4
    assert task.status == TaskStatus.PENDING.value


@pytest.mark.asyncio
async def test_confirm_putaway_warns_for_same_sku_lot_mismatch_by_default(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Lot Warning Tenant", code="LWT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-lot-warn",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add_all(
        [
            SKU(
                id="sku-putaway-lot-warn",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="DAN-LOT",
                name="Lot SKU",
            ),
            Location(
                id="loc-stage-lot-warn",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-lot-warn",
                barcode="STAGE-LOT-WARN-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-lot-warn",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-lot-warn",
                barcode="A-01-01-01-02",
                aisle="A",
                rack="01",
                level="01",
                position="02",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
            ),
        ]
    )
    db.add_all(
        [
            Inventory(
                id="inv-stage-lot-warn",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-stage-lot-warn",
                sku_id="sku-putaway-lot-warn",
                lot_number="LOT-B",
                quantity_on_hand=3,
            ),
            Inventory(
                id="inv-dest-lot-warn",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-dest-lot-warn",
                sku_id="sku-putaway-lot-warn",
                lot_number="LOT-A",
                quantity_on_hand=2,
            ),
            Task(
                id="task-putaway-lot-warn",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                sku_id="sku-putaway-lot-warn",
                quantity=3,
                source_location_id="loc-stage-lot-warn",
                reference_type="inbound_order",
                reference_id="order-putaway-lot-warn",
            ),
        ]
    )
    await db.flush()

    result = await PutawayService(db, tenant_id).confirm_putaway(
        "task-putaway-lot-warn",
        "loc-dest-lot-warn",
        user_id,
    )

    dest_rows = (
        (await db.execute(select(Inventory).where(Inventory.location_id == "loc-dest-lot-warn")))
        .scalars()
        .all()
    )

    assert result["success"] is True
    assert result["warnings"]
    assert "different lot or expiry" in result["warnings"][0]
    assert sum(row.quantity_on_hand for row in dest_rows) == 5


@pytest.mark.asyncio
async def test_confirm_putaway_can_block_same_sku_lot_mismatch_by_rule(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Lot Block Tenant", code="LBT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(
        Warehouse(
            id=warehouse_id,
            tenant_id=tenant_id,
            name="Budapest",
            code="BUD",
            address={"_planner_rules": {"lot_expiry_mismatch_policy": "block"}},
        )
    )
    db.add(
        Zone(
            id="zone-putaway-lot-block",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add_all(
        [
            SKU(
                id="sku-putaway-lot-block",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="DAN-LOT-BLOCK",
                name="Lot Block SKU",
            ),
            Location(
                id="loc-stage-lot-block",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-lot-block",
                barcode="STAGE-LOT-BLOCK-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-lot-block",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-lot-block",
                barcode="A-01-01-01-03",
                aisle="A",
                rack="01",
                level="01",
                position="03",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.OCCUPIED.value,
            ),
        ]
    )
    db.add_all(
        [
            Inventory(
                id="inv-stage-lot-block",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-stage-lot-block",
                sku_id="sku-putaway-lot-block",
                lot_number="LOT-B",
                quantity_on_hand=3,
            ),
            Inventory(
                id="inv-dest-lot-block",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-dest-lot-block",
                sku_id="sku-putaway-lot-block",
                lot_number="LOT-A",
                quantity_on_hand=2,
            ),
            Task(
                id="task-putaway-lot-block",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                sku_id="sku-putaway-lot-block",
                quantity=3,
                source_location_id="loc-stage-lot-block",
                reference_type="inbound_order",
                reference_id="order-putaway-lot-block",
            ),
        ]
    )
    await db.flush()

    result = await PutawayService(db, tenant_id).confirm_putaway(
        "task-putaway-lot-block",
        "loc-dest-lot-block",
        user_id,
    )

    source_inventory = await db.scalar(
        select(Inventory).where(Inventory.id == "inv-stage-lot-block")
    )

    assert result["success"] is False
    assert "different lot or expiry" in result["error"]
    assert source_inventory.quantity_on_hand == 3


@pytest.mark.asyncio
async def test_confirm_putaway_recovers_source_from_handling_unit_staging(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Source Tenant", code="SRC", contact_email="src@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-source",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-source",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SOURCE-001",
            name="Source SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-hu-source",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-source",
                barcode="STAGE-SOURCE-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-hu-source",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-source",
                barcode="A-01-01-03-01",
                aisle="A",
                rack="01",
                level="03",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        InboundOrder(
            id="order-putaway-source",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="ASN-PUTAWAY-SOURCE",
            status=InboundStatus.PUTAWAY.value,
        )
    )
    db.add(
        InboundOrderLine(
            id="line-putaway-source",
            tenant_id=tenant_id,
            order_id="order-putaway-source",
            sku_id="sku-putaway-source",
            line_number=1,
            quantity_expected=6,
            quantity_received=6,
        )
    )
    db.add(
        HandlingUnit(
            id="hu-putaway-source",
            tenant_id=tenant_id,
            order_id="order-putaway-source",
            order_line_id="line-putaway-source",
            sku_id="sku-putaway-source",
            unit_code="RCV-SOURCE-001",
            expected_qty=6,
            received_qty=6,
            status="putaway_pending",
            staging_location_id="loc-stage-hu-source",
        )
    )
    db.add(
        Inventory(
            id="inv-stage-hu-source",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-stage-hu-source",
            sku_id="sku-putaway-source",
            quantity_on_hand=6,
        )
    )
    db.add(
        Task(
            id="task-putaway-source",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-source",
            quantity=6,
            handling_unit_id="hu-putaway-source",
            source_location_id=None,
            reference_type="inbound_order",
            reference_id="order-putaway-source",
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    result = await service.confirm_putaway(
        "task-putaway-source",
        "loc-dest-hu-source",
        user_id,
    )

    task = await db.scalar(select(Task).where(Task.id == "task-putaway-source"))
    source_inventory = await db.scalar(
        select(Inventory).where(Inventory.id == "inv-stage-hu-source")
    )

    assert result["success"] is True
    assert task.source_location_id == "loc-stage-hu-source"
    assert source_inventory.quantity_on_hand == 0


@pytest.mark.asyncio
async def test_confirm_putaway_returns_clear_error_for_split_source_inventory(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Source Tenant", code="SRC", contact_email="src@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-source-split",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-source-split",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SOURCE-002",
            name="Source Split SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-source-split",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-source-split",
                barcode="STAGE-SOURCE-02",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-source-split",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-source-split",
                barcode="A-01-01-03-02",
                aisle="A",
                rack="01",
                level="03",
                position="02",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add_all(
        [
            Inventory(
                id="inv-stage-source-split-a",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-stage-source-split",
                sku_id="sku-putaway-source-split",
                lot_number="A",
                quantity_on_hand=3,
            ),
            Inventory(
                id="inv-stage-source-split-b",
                tenant_id=tenant_id,
                client_id=client_id,
                warehouse_id=warehouse_id,
                location_id="loc-stage-source-split",
                sku_id="sku-putaway-source-split",
                lot_number="B",
                quantity_on_hand=3,
            ),
        ]
    )
    db.add(
        Task(
            id="task-putaway-source-split",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-source-split",
            quantity=5,
            source_location_id="loc-stage-source-split",
            reference_type="inbound_order",
            reference_id="order-putaway-source-split",
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    result = await service.confirm_putaway(
        "task-putaway-source-split",
        "loc-dest-source-split",
        user_id,
    )

    assert result["success"] is False
    assert result["error_code"] == "putaway_source_stock_split"
    assert "split across multiple inventory records" in result["error"]


@pytest.mark.asyncio
async def test_confirm_putaway_rejects_split_quantity_mismatch(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Split Tenant", code="SPL", contact_email="split@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-putaway-split-bad",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-split-bad",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SPLIT-002",
            name="Split SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-split-bad",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split-bad",
                barcode="STAGE-SPLIT-02",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-split-bad-a",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split-bad",
                barcode="A-01-01-02-01",
                aisle="A",
                rack="01",
                level="02",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-dest-split-bad-b",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-putaway-split-bad",
                barcode="A-01-01-02-02",
                aisle="A",
                rack="01",
                level="02",
                position="02",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        Inventory(
            id="inv-stage-split-bad",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-stage-split-bad",
            sku_id="sku-putaway-split-bad",
            quantity_on_hand=5,
        )
    )
    db.add(
        Task(
            id="task-putaway-split-bad",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-putaway-split-bad",
            quantity=5,
            source_location_id="loc-stage-split-bad",
            reference_type="inbound_order",
            reference_id="order-putaway-split-bad",
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    result = await service.confirm_putaway(
        "task-putaway-split-bad",
        "loc-dest-split-bad-a",
        user_id,
        allocations=[
            {"location_id": "loc-dest-split-bad-a", "quantity": 3},
            {"location_id": "loc-dest-split-bad-b", "quantity": 1},
        ],
    )

    assert result["success"] is False
    assert result["error_code"] == "putaway_allocation_quantity_mismatch"
    assert "must equal the task quantity" in result["error"]


@pytest.mark.asyncio
async def test_suggest_putaway_excludes_current_staging_location(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Split Tenant", code="SPL", contact_email="split@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-suggest-split",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone A",
            code="ZA",
        )
    )
    db.add(
        SKU(
            id="sku-suggest-split",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SUG-001",
            name="Suggest SKU",
        )
    )
    db.add_all(
        [
            Location(
                id="loc-stage-suggest",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-suggest-split",
                barcode="DOCK-01",
                aisle="DOCK",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="loc-storage-suggest",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-suggest-split",
                barcode="A-01-01-01-01",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        Inventory(
            id="inv-stage-suggest",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-stage-suggest",
            sku_id="sku-suggest-split",
            quantity_on_hand=5,
        )
    )
    await db.flush()

    service = PutawayService(db, tenant_id)
    suggestions = await service.suggest_location(
        warehouse_id=warehouse_id,
        sku_id="sku-suggest-split",
        quantity=5,
        exclude_location_id="loc-stage-suggest",
    )

    assert all(suggestion["location_id"] != "loc-stage-suggest" for suggestion in suggestions)


@pytest.mark.asyncio
async def test_list_tasks_exposes_execution_guidance_and_handling_unit_identity(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Receiving Tenant",
            code="RCT",
            contact_email="ops@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-task-list-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-task-list-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-006",
            name="HU Item 6",
        )
    )
    db.add(
        Location(
            id="staging-task-list-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-task-list-1",
            barcode="STAGE-TASK-LIST-01",
            aisle="STAGE",
            rack="01",
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
        order_number="ASN-TASK-LIST-001",
        lines=[
            {"sku_id": "sku-task-list-1", "quantity": 3, "external_carton_mark": "CARTON-LIST-001"}
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="CARTON-LIST-001",
        quantity_received=3,
        quantity_damaged=0,
        staging_location_id="staging-task-list-1",
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["receiving.execute", "master_data.manage"],
        exp=datetime.now(UTC),
    )
    tasks = await list_tasks(
        warehouse_id=warehouse_id,
        status=TaskStatus.PENDING.value,
        assigned_type=None,
        assigned_to=None,
        task_type=TaskType.PUTAWAY.value,
        limit=100,
        current_user=current_user,
        db=db,
    )

    assert len(tasks) == 1
    assert tasks[0].created_at is not None
    assert tasks[0].handling_unit_code == "RCV-ASN-TASK-LIST-001-001"
    assert tasks[0].handling_unit_status == "putaway_pending"
    assert tasks[0].external_carton_mark == "CARTON-LIST-001"
    assert tasks[0].agv_eligible is False
    assert tasks[0].execution_reason == "no_agv_storage_available"


@pytest.mark.asyncio
async def test_putaway_repair_is_explicit_and_idempotent(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Repair Tenant",
            code="RPT",
            contact_email="repair@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-task-repair-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-task-repair-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-REPAIR-001",
            name="Repair Item",
        )
    )
    db.add(
        Location(
            id="staging-task-repair-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-task-repair-1",
            barcode="STAGE-TASK-REPAIR-01",
            aisle="STAGE",
            rack="01",
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
        order_number="ASN-TASK-REPAIR-001",
        lines=[
            {
                "sku_id": "sku-task-repair-1",
                "quantity": 4,
                "external_carton_mark": "CARTON-REPAIR-001",
            }
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="CARTON-REPAIR-001",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-task-repair-1",
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    await db.execute(
        delete(Task).where(
            Task.tenant_id == tenant_id,
            Task.reference_type == "inbound_order",
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["receiving.execute", "master_data.manage"],
        exp=datetime.now(UTC),
    )
    tasks_before = await list_tasks(
        warehouse_id=warehouse_id,
        status=TaskStatus.PENDING.value,
        assigned_type=None,
        assigned_to=None,
        task_type=TaskType.PUTAWAY.value,
        limit=100,
        current_user=current_user,
        db=db,
    )

    task_count_before = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant_id,
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    assert tasks_before == []
    assert task_count_before == 0

    repair_result = await repair_putaway_task_records(
        PutawayTaskRepairRequest(inbound_order_id=order.id),
        current_user=current_user,
        db=db,
    )
    assert repair_result.scanned_orders == 1
    assert repair_result.created_tasks == 1
    assert repair_result.updated_tasks == 0
    assert repair_result.errors == []

    tasks_after = await list_tasks(
        warehouse_id=warehouse_id,
        status=TaskStatus.PENDING.value,
        assigned_type=None,
        assigned_to=None,
        task_type=TaskType.PUTAWAY.value,
        limit=100,
        current_user=current_user,
        db=db,
    )
    assert len(tasks_after) == 1
    assert tasks_after[0].handling_unit_code == "RCV-ASN-TASK-REPAIR-001-001"
    assert tasks_after[0].quantity == 4

    second_repair = await repair_putaway_task_records(
        PutawayTaskRepairRequest(inbound_order_id=order.id),
        current_user=current_user,
        db=db,
    )
    assert second_repair.scanned_orders == 1
    assert second_repair.created_tasks == 0
    assert second_repair.updated_tasks == 0


@pytest.mark.asyncio
async def test_confirm_putaway_marks_handling_unit_stored(
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
            id="zone-putaway-store",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-putaway-store",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-STORE",
            name="HU Stored",
        )
    )
    db.add(
        Location(
            id="staging-putaway-store",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-putaway-store",
            barcode="STAGE-PUTAWAY-STORE-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        Location(
            id="storage-putaway-store",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-putaway-store",
            barcode="A-01-01-01-09",
            aisle="A",
            rack="01",
            level="01",
            position="09",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-PUTAWAY-STORED-001",
        lines=[
            {
                "sku_id": "sku-putaway-store",
                "quantity": 4,
                "external_tracking_number": "TRACK-STORED-001",
            }
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="TRACK-STORED-001",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-putaway-store",
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    task = await db.scalar(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )
    handling_unit = await db.scalar(select(HandlingUnit).where(HandlingUnit.order_id == order.id))
    package = await db.scalar(select(InboundPackage).where(InboundPackage.order_id == order.id))
    assert task is not None
    assert handling_unit is not None
    assert package is not None
    assert handling_unit.status == "putaway_pending"
    assert package.status == "putaway_pending"

    putaway_service = PutawayService(db, tenant_id)
    result = await putaway_service.confirm_putaway(
        task_id=task.id,
        destination_location_id="storage-putaway-store",
        user_id=user_id,
    )

    assert result["success"] is True
    assert result["handling_unit_status"] == "stored"
    assert handling_unit.status == "stored"
    assert package.status == "stored"
