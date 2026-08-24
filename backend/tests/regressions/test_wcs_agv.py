"""Regression tests: WCS and AGV integration (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.integrations import (
    WcsCertificationTaskRequest,
    WcsConfigUpdateRequest,
    WcsPointMapping,
    WcsPointMappingImportRequest,
    WcsPointMappingRequest,
    create_wcs_certification_task,
    import_wcs_point_mappings,
    list_wcs_point_mappings,
    preview_wcs_certification_task,
    preview_wcs_config_update,
    update_wcs_config,
    validate_wcs_point_mappings,
    wcs_taskfinish_webhook,
)
from app.core.security import TokenPayload, UserRole
from app.models.client import Client
from app.models.inventory import SKU, InventoryTransaction
from app.models.order import HandlingUnit, InboundOrder, InboundOrderLine, ReceivingLabel
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.models.wcs import WcsTaskBinding
from app.services.agv_service import AGVService
from app.services.receiving_service import ReceivingService
from app.services.wcs_adapter_service import WcsAdapterService


@pytest.mark.asyncio
async def test_agv_pending_tasks_include_handling_unit_context(
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
            id="zone-agv-hu-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-agv-hu-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-004",
            name="HU Item 4",
        )
    )
    db.add(
        Location(
            id="staging-agv-hu-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agv-hu-1",
            barcode="STAGE-AGV-HU-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
            is_agv_accessible=True,
            coordinate_x=1,
            coordinate_y=2,
            coordinate_z=0,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-AGV-HU-001",
        lines=[
            {
                "sku_id": "sku-agv-hu-1",
                "quantity": 8,
                "external_tracking_number": "AGV-TRACK-001",
            }
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="AGV-TRACK-001",
        quantity_received=8,
        quantity_damaged=1,
        staging_location_id="staging-agv-hu-1",
        measured_weight_kg=12.5,
        package_count=2,
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    agv_service = AGVService(db, tenant_id)
    tasks = await agv_service.get_pending_tasks(warehouse_id, [TaskType.PUTAWAY.value], limit=10)

    assert len(tasks) == 1
    assert tasks[0]["execution_mode"] == AssignedType.HUMAN.value
    assert tasks[0]["handling_unit_code"] == "RCV-ASN-AGV-HU-001-001"
    assert tasks[0]["handling_unit_status"] == "putaway_pending"
    assert tasks[0]["package_count"] == 2
    assert tasks[0]["measured_weight_kg"] == 12.5
    assert tasks[0]["external_tracking_number"] == "AGV-TRACK-001"
    assert tasks[0]["handling_unit"] is not None
    assert tasks[0]["handling_unit"]["unit_type"] == "carton"
    assert tasks[0]["handling_unit"]["external_tracking_number"] == "AGV-TRACK-001"
    assert tasks[0]["handling_unit"]["package_count"] == 2


@pytest.mark.asyncio
async def test_complete_receiving_marks_putaway_task_as_agv_when_flow_is_ready(
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
    db.add(
        Warehouse(
            id=warehouse_id,
            tenant_id=tenant_id,
            name="Budapest",
            code="BUD",
            address={"_planner_rules": {"agv_max_payload_kg": 20}},
        )
    )
    db.add(
        Zone(
            id="zone-agv-decision-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Zone(
            id="zone-agv-decision-2",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="AGV",
            code="AGV",
        )
    )
    db.add(
        SKU(
            id="sku-agv-decision-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-005",
            name="HU Item 5",
        )
    )
    db.add(
        Location(
            id="staging-agv-decision-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agv-decision-1",
            barcode="STAGE-AGV-DEC-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
            is_agv_accessible=True,
        )
    )
    db.add(
        Location(
            id="storage-agv-decision-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agv-decision-2",
            barcode="A-01-01-01-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
            is_agv_accessible=True,
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-AGV-DECISION-001",
        lines=[{"sku_id": "sku-agv-decision-1", "quantity": 4}],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="RCV-ASN-AGV-DECISION-001-001",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-agv-decision-1",
        measured_weight_kg=12.5,
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    task = await db.scalar(
        select(Task).where(
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
        )
    )

    assert task is not None
    assert task.execution_mode == AssignedType.AGV.value


@pytest.mark.asyncio
async def test_agv_pending_backfills_missing_handling_unit_id(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-agv-backfill",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-agv-backfill",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-007",
            name="HU Item 7",
        )
    )
    db.add(
        Location(
            id="staging-agv-backfill",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agv-backfill",
            barcode="STAGE-AGV-BACKFILL-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        InboundOrder(
            id="order-agv-backfill",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="ASN-AGV-BACKFILL-001",
            status="putaway",
        )
    )
    db.add(
        InboundOrderLine(
            id="line-agv-backfill",
            tenant_id=tenant_id,
            order_id="order-agv-backfill",
            sku_id="sku-agv-backfill",
            quantity_expected=4,
            quantity_received=4,
            quantity_damaged=0,
            staging_location_id="staging-agv-backfill",
        )
    )
    db.add(
        HandlingUnit(
            id="hu-agv-backfill",
            tenant_id=tenant_id,
            order_id="order-agv-backfill",
            order_line_id="line-agv-backfill",
            sku_id="sku-agv-backfill",
            unit_code="RCV-ASN-AGV-BACKFILL-001-001",
            unit_type="carton",
            expected_qty=4,
            received_qty=4,
            status="putaway_pending",
            package_count=1,
        )
    )
    db.add(
        Task(
            id="task-agv-backfill",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-agv-backfill",
            quantity=4,
            source_location_id="staging-agv-backfill",
            reference_type="inbound_order",
            reference_id="order-agv-backfill",
            assigned_type=AssignedType.UNASSIGNED.value,
            execution_mode=AssignedType.HUMAN.value,
        )
    )
    await db.flush()

    agv_service = AGVService(db, tenant_id)
    tasks = await agv_service.get_pending_tasks(warehouse_id, [TaskType.PUTAWAY.value], limit=10)

    matching = next(item for item in tasks if item["task_id"] == "task-agv-backfill")
    task_row = await db.scalar(select(Task).where(Task.id == "task-agv-backfill"))

    assert matching["handling_unit_id"] == "hu-agv-backfill"
    assert matching["handling_unit_code"] == "RCV-ASN-AGV-BACKFILL-001-001"
    assert matching["handling_unit_status"] == "putaway_pending"
    assert matching["package_count"] == 1
    assert matching["handling_unit"] is not None
    assert matching["handling_unit"]["unit_code"] == "RCV-ASN-AGV-BACKFILL-001-001"
    assert task_row.handling_unit_id == "hu-agv-backfill"


@pytest.mark.asyncio
async def test_agv_pending_backfills_single_candidate_when_source_mismatch(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-agv-fallback",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-agv-fallback",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-008",
            name="HU Item 8",
        )
    )
    db.add_all(
        [
            Location(
                id="staging-agv-fallback-real",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-agv-fallback",
                barcode="STAGE-AGV-FALLBACK-REAL",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="staging-agv-fallback-old",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-agv-fallback",
                barcode="STAGE-AGV-FALLBACK-OLD",
                aisle="STAGE",
                rack="02",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    db.add(
        InboundOrder(
            id="order-agv-fallback",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="ASN-AGV-FALLBACK-001",
            status="putaway",
        )
    )
    db.add(
        InboundOrderLine(
            id="line-agv-fallback",
            tenant_id=tenant_id,
            order_id="order-agv-fallback",
            sku_id="sku-agv-fallback",
            quantity_expected=4,
            quantity_received=4,
            quantity_damaged=0,
            staging_location_id="staging-agv-fallback-real",
        )
    )
    db.add(
        HandlingUnit(
            id="hu-agv-fallback",
            tenant_id=tenant_id,
            order_id="order-agv-fallback",
            order_line_id="line-agv-fallback",
            sku_id="sku-agv-fallback",
            unit_code="RCV-ASN-AGV-FALLBACK-001-001",
            unit_type="carton",
            expected_qty=4,
            received_qty=4,
            status="putaway_pending",
            package_count=1,
        )
    )
    db.add(
        Task(
            id="task-agv-fallback",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-agv-fallback",
            quantity=4,
            source_location_id="staging-agv-fallback-old",
            reference_type="inbound_order",
            reference_id="order-agv-fallback",
            assigned_type=AssignedType.UNASSIGNED.value,
            execution_mode=AssignedType.HUMAN.value,
        )
    )
    await db.flush()

    agv_service = AGVService(db, tenant_id)
    tasks = await agv_service.get_pending_tasks(warehouse_id, [TaskType.PUTAWAY.value], limit=10)
    matching = next(item for item in tasks if item["task_id"] == "task-agv-fallback")
    task_row = await db.scalar(select(Task).where(Task.id == "task-agv-fallback"))

    assert matching["handling_unit_id"] == "hu-agv-fallback"
    assert matching["handling_unit_code"] == "RCV-ASN-AGV-FALLBACK-001-001"
    assert matching["handling_unit"] is not None
    assert task_row.handling_unit_id == "hu-agv-fallback"


@pytest.mark.asyncio
async def test_agv_pending_creates_handling_unit_from_legacy_label(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Receiving Tenant", code="RCT", contact_email="ops@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-agv-legacy",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-agv-legacy",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-009",
            name="HU Item 9",
        )
    )
    db.add(
        InboundOrder(
            id="order-agv-legacy",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="ASN-AGV-LEGACY-001",
            status="putaway",
        )
    )
    db.add(
        InboundOrderLine(
            id="line-agv-legacy",
            tenant_id=tenant_id,
            order_id="order-agv-legacy",
            sku_id="sku-agv-legacy",
            quantity_expected=6,
            quantity_received=6,
            quantity_damaged=1,
            staging_location_id="staging-agv-legacy",
            measured_weight_kg=12.5,
            package_count=2,
        )
    )
    db.add(
        Location(
            id="staging-agv-legacy",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agv-legacy",
            barcode="STAGE-AGV-LEGACY-01",
            aisle="STAGE",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        ReceivingLabel(
            id="label-agv-legacy",
            tenant_id=tenant_id,
            order_id="order-agv-legacy",
            order_line_id="line-agv-legacy",
            sku_id="sku-agv-legacy",
            label_code="RCV-ASN-AGV-LEGACY-001-001",
            label_type="line",
            expected_qty=6,
            received_qty=5,
            status="received",
            external_tracking_number="TRK-LEGACY-001",
            external_carton_mark="CTN-LEGACY-001",
            external_customer_barcode="CUS-LEGACY-001",
        )
    )
    db.add(
        Task(
            id="task-agv-legacy",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            sku_id="sku-agv-legacy",
            quantity=5,
            source_location_id="staging-agv-legacy",
            reference_type="inbound_order",
            reference_id="order-agv-legacy",
            assigned_type=AssignedType.UNASSIGNED.value,
            execution_mode=AssignedType.HUMAN.value,
        )
    )
    await db.flush()

    agv_service = AGVService(db, tenant_id)
    tasks = await agv_service.get_pending_tasks(warehouse_id, [TaskType.PUTAWAY.value], limit=10)
    matching = next(item for item in tasks if item["task_id"] == "task-agv-legacy")
    task_row = await db.scalar(select(Task).where(Task.id == "task-agv-legacy"))
    handling_unit = await db.scalar(
        select(HandlingUnit).where(HandlingUnit.receiving_label_id == "label-agv-legacy")
    )

    assert matching["handling_unit_id"] == handling_unit.id
    assert matching["handling_unit_code"] == "RCV-ASN-AGV-LEGACY-001-001"
    assert matching["package_count"] == 2
    assert matching["measured_weight_kg"] == 12.5
    assert matching["source_barcode"] == "STAGE-AGV-LEGACY-01"
    assert matching["destination_barcode"] is None
    assert matching["handling_unit"]["external_tracking_number"] == "TRK-LEGACY-001"
    assert task_row.handling_unit_id == handling_unit.id
    assert handling_unit is not None
    assert handling_unit.status == "putaway_pending"
    assert handling_unit.received_qty == 5


@pytest.mark.asyncio
async def test_wcs_config_update_preview_and_apply_preserves_omitted_secrets(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Config Tenant", code="WCSCFG", contact_email="wcs@example.com"))
    db.add(
        Warehouse(
            id="wcs-config-wh",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs-simulator.invalid",
                    "callback_url": "https://api.example.test/old-callback",
                    "access_token": "existing-secret-token",
                    "scode": "DAL",
                    "point_mappings": {"A-01": {"point_code": "DAL-STO-A-01", "agv_reachable": True}},
                }
            },
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub="wcs-config-admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    preview = await preview_wcs_config_update(
        body=WcsConfigUpdateRequest(
            warehouse_id="wcs-config-wh",
            base_url="https://wcs-sandbox.example.com/",
            callback_url="https://api.maxsmartwms.online/api/v1/integrations/wcs/webhook/t/taskfinish",
        ),
        current_user=current_user,
        db=db,
    )

    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["writes"] is False
    assert preview["changed_keys"] == ["base_url", "callback_url"]
    assert preview["proposed_config"]["access_token"] == "***redacted***"

    warehouse = await db.scalar(select(Warehouse).where(Warehouse.id == "wcs-config-wh"))
    assert warehouse.address["_wcs"]["base_url"] == "https://wcs-simulator.invalid"
    assert warehouse.address["_wcs"]["access_token"] == "existing-secret-token"

    applied = await update_wcs_config(
        body=WcsConfigUpdateRequest(
            warehouse_id="wcs-config-wh",
            base_url="https://wcs-sandbox.example.com/",
            callback_url="https://api.maxsmartwms.online/api/v1/integrations/wcs/webhook/t/taskfinish",
        ),
        current_user=current_user,
        db=db,
    )

    assert applied["ok"] is True
    assert applied["status"] == "configured"
    assert applied["config"]["access_token"] == "***redacted***"
    await db.refresh(warehouse)
    assert warehouse.address["_wcs"]["base_url"] == "https://wcs-sandbox.example.com"
    assert warehouse.address["_wcs"]["access_token"] == "existing-secret-token"
    assert warehouse.address["_wcs"]["point_mappings"]["A-01"]["point_code"] == "DAL-STO-A-01"


@pytest.mark.asyncio
async def test_wcs_certification_task_preview_and_create_requires_confirm(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="WCS Certification Tenant",
            code="WCSCERT",
            contact_email="wcscert@example.com",
        )
    )
    db.add(Warehouse(id="wcs-cert-wh", tenant_id=tenant_id, name="Dallas", code="DAL"))
    db.add(
        Zone(
            id="wcs-cert-zone",
            tenant_id=tenant_id,
            warehouse_id="wcs-cert-wh",
            name="Cert",
            code="CERT",
        )
    )
    db.add_all(
        [
            Location(
                id="wcs-cert-src",
                tenant_id=tenant_id,
                warehouse_id="wcs-cert-wh",
                zone_id="wcs-cert-zone",
                barcode="DAL-CERT-SRC",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="wcs-cert-dst",
                tenant_id=tenant_id,
                warehouse_id="wcs-cert-wh",
                zone_id="wcs-cert-zone",
                barcode="DAL-CERT-DST",
                aisle="B",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            SKU(
                id="wcs-cert-sku",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="WCS-CERT-001",
                name="WCS Certification SKU",
            ),
        ]
    )
    await db.flush()
    current_user = TokenPayload(
        sub="wcs-cert-admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    preview = await preview_wcs_certification_task(
        body=WcsCertificationTaskRequest(
            warehouse_id="wcs-cert-wh",
            source_location_id="wcs-cert-src",
            destination_location_id="wcs-cert-dst",
            sku_id="wcs-cert-sku",
            quantity=2,
        ),
        current_user=current_user,
        db=db,
    )
    pending_before = await db.scalar(
        select(func.count()).select_from(Task).where(Task.tenant_id == tenant_id)
    )

    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["writes"] is False
    assert preview["planned_task"]["reference_type"] == "wcs_sandbox_cert"
    assert preview["planned_task"]["task_type"] == TaskType.MOVE.value
    assert preview["planned_task"]["assigned_type"] == AssignedType.UNASSIGNED.value
    assert preview["planned_task"]["execution_mode"] == AssignedType.AGV.value
    assert preview["planned_task"]["lpn"].startswith("WCS-SBX-CERT-")
    assert preview["planned_request"]["external_wcs_call"] is False
    assert pending_before == 0

    with pytest.raises(HTTPException) as missing_confirm:
        await create_wcs_certification_task(
            body=WcsCertificationTaskRequest(
                warehouse_id="wcs-cert-wh",
                source_location_id="wcs-cert-src",
                destination_location_id="wcs-cert-dst",
                sku_id="wcs-cert-sku",
                quantity=2,
            ),
            current_user=current_user,
            db=db,
        )
    assert missing_confirm.value.status_code == 400
    assert missing_confirm.value.detail["code"] == "confirm_create_required"

    created = await create_wcs_certification_task(
        body=WcsCertificationTaskRequest(
            warehouse_id="wcs-cert-wh",
            source_location_id="wcs-cert-src",
            destination_location_id="wcs-cert-dst",
            sku_id="wcs-cert-sku",
            quantity=2,
            confirm_create=True,
        ),
        current_user=current_user,
        db=db,
    )
    created_task = await db.scalar(
        select(Task).where(Task.tenant_id == tenant_id, Task.id == created["task"]["id"])
    )

    assert created["ok"] is True
    assert created["created"] is True
    assert created["dispatch_block"]["external_wcs_call"] is False
    assert created_task is not None
    assert created_task.task_type == TaskType.MOVE.value
    assert created_task.status == TaskStatus.PENDING.value
    assert created_task.assigned_type == AssignedType.UNASSIGNED.value
    assert created_task.execution_mode == AssignedType.AGV.value
    assert created_task.reference_type == "wcs_sandbox_cert"
    assert created_task.quantity == 2
    assert created_task.source_location_id == "wcs-cert-src"
    assert created_task.destination_location_id == "wcs-cert-dst"


@pytest.mark.asyncio
async def test_wcs_certification_task_preview_blocks_non_sandbox_scope(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Scope Tenant", code="WCSSC", contact_email="wcssc@example.com"))
    db.add(Warehouse(id="wcs-scope-wh", tenant_id=tenant_id, name="Dallas", code="DAL"))
    db.add(
        Zone(
            id="wcs-scope-zone",
            tenant_id=tenant_id,
            warehouse_id="wcs-scope-wh",
            name="Scope",
            code="SCP",
        )
    )
    db.add_all(
        [
            Location(
                id="wcs-scope-src",
                tenant_id=tenant_id,
                warehouse_id="wcs-scope-wh",
                zone_id="wcs-scope-zone",
                barcode="DAL-SCOPE-SRC",
                aisle="A",
                rack="01",
                level="01",
                position="01",
            ),
            Location(
                id="wcs-scope-dst",
                tenant_id=tenant_id,
                warehouse_id="wcs-scope-wh",
                zone_id="wcs-scope-zone",
                barcode="DAL-SCOPE-DST",
                aisle="B",
                rack="01",
                level="01",
                position="01",
            ),
            SKU(
                id="wcs-scope-sku",
                tenant_id=tenant_id,
                client_id=client_id,
                sku_code="WCS-SCOPE-001",
                name="WCS Scope SKU",
            ),
        ]
    )
    await db.flush()
    current_user = TokenPayload(
        sub="wcs-scope-admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    with pytest.raises(HTTPException) as exc_info:
        await preview_wcs_certification_task(
            body=WcsCertificationTaskRequest(
                warehouse_id="wcs-scope-wh",
                source_location_id="wcs-scope-src",
                destination_location_id="wcs-scope-dst",
                sku_id="wcs-scope-sku",
                certification_scope="production_dispatch",
            ),
            current_user=current_user,
            db=db,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "invalid_certification_scope"


@pytest.mark.asyncio
async def test_wcs_adapter_dispatches_task_and_applies_completion_callback(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(Tenant(id=tenant_id, name="WCS Tenant", code="WCS", contact_email="wcs@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-1",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                    "callback_url": "https://wms.example.test/api/v1/integrations/wcs/webhook/t/taskfinish",
                    "scode": "DALLAS",
                    "default_pallet_spec": "GMA",
                    "task_type_map": {"putaway": "AGV上架"},
                    "point_mappings": {
                        "wcs-source-1": {
                            "location_id": "wcs-source-1",
                            "location_barcode": "DOCK-27",
                            "point_code": "WCS-DOCK-27",
                            "buffer_code": "DOCK",
                            "aisle_group": "INBOUND",
                            "agv_reachable": True,
                        },
                        "wcs-dest-1": {
                            "location_id": "wcs-dest-1",
                            "location_barcode": "DAL-A-01-01-01-01",
                            "point_code": "WCS-DAL-A-001",
                            "buffer_code": "A",
                            "aisle_group": "A01",
                            "agv_reachable": True,
                        },
                    },
                }
            },
        )
    )
    db.add(Zone(id="wcs-zone-1", tenant_id=tenant_id, warehouse_id="wcs-wh-1", name="A", code="A"))
    db.add_all(
        [
            Location(
                id="wcs-source-1",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-1",
                zone_id="wcs-zone-1",
                barcode="DOCK-27",
                aisle="D",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
            Location(
                id="wcs-dest-1",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-1",
                zone_id="wcs-zone-1",
                barcode="DAL-A-01-01-01-01",
                aisle="01",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
        ]
    )
    db.add(
        Task(
            id="wcs-task-1",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-1",
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=3,
            sku_id="sku-wcs-1",
            quantity=1,
            lpn="PALLET-WCS-001",
            source_location_id="wcs-source-1",
            destination_location_id="wcs-dest-1",
            assigned_type=AssignedType.UNASSIGNED.value,
            reference_type="inbound_order",
            reference_id="inb-wcs-1",
        )
    )
    await db.flush()

    captured: dict = {}

    async def fake_post_transport_task(self, config: dict, payload: dict) -> dict:
        captured["config"] = config
        captured["payload"] = payload
        return {
            "success": "true",
            "data": {"wtaskinfoTid": "4093", "wtaskinfoPsn": "PALLET-WCS-001"},
        }

    monkeypatch.setattr(WcsAdapterService, "_post_transport_task", fake_post_transport_task)

    service = WcsAdapterService(db, tenant_id)
    config = await service.read_config("wcs-wh-1")
    assert config["config"]["access_token"] == "***redacted***"
    assert config["point_mapping_count"] == 2

    preview = await service.preview_dispatch_task("wcs-task-1")
    assert preview["dry_run"] is True
    assert preview["gate"]["ok"] is True
    assert preview["planned_request"]["external_wcs_call"] is False
    assert preview["planned_request"]["body"]["startPos"] == "WCS-DOCK-27"

    dispatch = await service.dispatch_task("wcs-task-1")
    assert dispatch["success"] is True
    assert dispatch["wcs_task_id"] == "4093"
    assert captured["payload"]["startPos"] == "WCS-DOCK-27"
    assert captured["payload"]["endPos"] == "WCS-DAL-A-001"
    assert captured["payload"]["wtaskinfoType"] == "AGV上架"
    assert captured["payload"]["wtaskinfoOrder"] == "3"
    assert captured["payload"]["wtaskinfoPsn"] == "PALLET-WCS-001"
    assert captured["payload"]["wtaskinfoPalletSpec"] == "GMA"
    assert captured["payload"]["wtaskinfoOutparam"]["source_wcs"]["buffer_code"] == "DOCK"

    in_progress = await service.apply_task_callback(
        {
            "taskTid": 4093,
            "stepTid": 4121,
            "taskPsn": "PALLET-WCS-001",
            "stepStatus": 20,
            "stepStatusName": "执行中",
            "stepAgvIp": "agv-01",
        }
    )
    task = await db.scalar(select(Task).where(Task.id == "wcs-task-1"))
    assert in_progress["status"] == "in_progress"
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.assigned_to == "agv:agv-01"

    bindings = await service.list_bindings(task_id="wcs-task-1")
    assert bindings["count"] == 1
    assert bindings["items"][0]["wcs_task_id"] == "4093"

    replay = await service.preview_task_callback(
        {
            "taskTid": 4093,
            "stepTid": 4121,
            "taskPsn": "PALLET-WCS-001",
            "stepStatus": 30,
            "stepStatusName": "已完成",
            "stepAgvIp": "agv-01",
        }
    )
    assert replay["dry_run"] is True
    assert replay["mapped_wcs_status"] == "completed"
    assert replay["task_status_before"] == TaskStatus.IN_PROGRESS.value
    assert replay["task_status_after"] == TaskStatus.COMPLETED.value

    completed = await service.apply_task_callback(
        {
            "taskTid": 4093,
            "stepTid": 4121,
            "taskPsn": "PALLET-WCS-001",
            "stepStatus": 30,
            "stepStatusName": "已完成",
            "stepAgvIp": "agv-01",
        }
    )
    assert completed["status"] == "completed"
    assert task.status == TaskStatus.COMPLETED.value
    binding = await db.scalar(select(WcsTaskBinding).where(WcsTaskBinding.task_id == "wcs-task-1"))
    assert binding is not None
    assert binding.wcs_task_id == "4093"
    assert binding.last_step_status == 30
    assert binding.last_callback_payload["stepStatusName"] == "已完成"

    await service.apply_task_callback(
        {
            "taskTid": 4093,
            "stepTid": 4121,
            "taskPsn": "PALLET-WCS-001",
            "stepStatus": 30,
            "stepStatusName": "已完成",
            "stepAgvIp": "agv-01",
        }
    )
    transaction_count = await db.scalar(
        select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.reference_id == "inb-wcs-1"
        )
    )
    assert transaction_count == 1


@pytest.mark.asyncio
async def test_wcs_taskfinish_webhook_applies_tenant_context_before_matching_binding(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(Tenant(id=tenant_id, name="WCS Webhook Tenant", code="WCW", contact_email="wcw@example.com"))
    db.add(Warehouse(id="wcs-wh-webhook", tenant_id=tenant_id, name="Dallas", code="DAL"))
    db.add(
        Task(
            id="wcs-task-webhook",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-webhook",
            task_type=TaskType.MOVE.value,
            status=TaskStatus.ASSIGNED.value,
            priority=5,
            quantity=1,
            assigned_type=AssignedType.AGV.value,
            assigned_to="agv:wcs",
        )
    )
    db.add(
        WcsTaskBinding(
            tenant_id=tenant_id,
            task_id="wcs-task-webhook",
            warehouse_id="wcs-wh-webhook",
            wcs_task_id="7001",
            task_psn="PALLET-WEBHOOK",
            start_pos="DOCK-27",
            end_pos="DAL-A-01",
            status="queued",
        )
    )
    await db.flush()

    context_calls: list[dict] = []

    async def fake_apply_session_context(
        session: AsyncSession,
        tenant_id: str | None = None,
        is_platform_admin: bool = False,
    ) -> None:
        context_calls.append({"tenant_id": tenant_id, "is_platform_admin": is_platform_admin})

    class FakeRequest:
        async def json(self) -> dict:
            return {
                "taskTid": 7001,
                "taskPsn": "PALLET-WEBHOOK",
                "stepStatus": 20,
                "stepStatusName": "执行中",
                "stepAgvIp": "agv-sandbox-01",
            }

    monkeypatch.setattr(
        "app.api.v1.endpoints.integrations.apply_session_context",
        fake_apply_session_context,
    )

    result = await wcs_taskfinish_webhook(tenant_id=tenant_id, request=FakeRequest(), db=db)

    task = await db.scalar(select(Task).where(Task.id == "wcs-task-webhook"))
    binding = await db.scalar(select(WcsTaskBinding).where(WcsTaskBinding.task_id == "wcs-task-webhook"))
    assert context_calls == [{"tenant_id": tenant_id, "is_platform_admin": False}]
    assert result["code"] == 0
    assert result["status"] == "in_progress"
    assert task.status == TaskStatus.IN_PROGRESS.value
    assert task.assigned_to == "agv:agv-sandbox-01"
    assert binding.last_step_status == 20
    assert binding.last_callback_payload["stepStatusName"] == "执行中"


@pytest.mark.asyncio
async def test_wcs_adapter_blocks_dispatch_without_point_mapping(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Gate Tenant", code="WCG", contact_email="wcg@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-gate",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                    "callback_url": "https://wms.example.test/callback",
                    "point_mappings": {},
                }
            },
        )
    )
    db.add(Zone(id="wcs-zone-gate", tenant_id=tenant_id, warehouse_id="wcs-wh-gate", name="A", code="A"))
    db.add_all(
        [
            Location(
                id="wcs-source-gate",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-gate",
                zone_id="wcs-zone-gate",
                barcode="DOCK-GATE",
                aisle="D",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
            Location(
                id="wcs-dest-gate",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-gate",
                zone_id="wcs-zone-gate",
                barcode="A-GATE",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
        ]
    )
    db.add(
        Task(
            id="wcs-task-gate",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-gate",
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            quantity=1,
            source_location_id="wcs-source-gate",
            destination_location_id="wcs-dest-gate",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()

    preview = await WcsAdapterService(db, tenant_id).preview_dispatch_task("wcs-task-gate")
    gate = preview["gate"]
    assert gate["ok"] is False
    assert "issues" in gate
    assert [issue["code"] for issue in gate["issue_details"]] == [
        "missing_source_point_code",
        "source_point_not_wcs_agv_reachable",
        "missing_destination_point_code",
        "destination_point_not_wcs_agv_reachable",
    ]
    assert gate["source"]["point_code"] is None
    assert gate["destination"]["point_type"] == LocationType.STORAGE.value
    assert gate["recovery_actions"][0]["action"] == "map_wcs_point_code"

    with pytest.raises(Exception, match="no WCS point_code mapping"):
        await WcsAdapterService(db, tenant_id).dispatch_task("wcs-task-gate")


@pytest.mark.asyncio
async def test_wcs_point_mapping_validation_blocks_duplicate_point_codes(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Map Tenant", code="WCM", contact_email="wcm@example.com"))
    warehouse = Warehouse(id="wcs-wh-map", tenant_id=tenant_id, name="Dallas", code="DAL")
    db.add(warehouse)
    db.add(Zone(id="wcs-zone-map", tenant_id=tenant_id, warehouse_id="wcs-wh-map", name="A", code="A"))
    db.add_all(
        [
            Location(
                id="wcs-map-1",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-map",
                zone_id="wcs-zone-map",
                barcode="A-01-01",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                is_agv_accessible=True,
            ),
            Location(
                id="wcs-map-2",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-map",
                zone_id="wcs-zone-map",
                barcode="A-01-02",
                aisle="A",
                rack="01",
                level="01",
                position="02",
                is_agv_accessible=True,
            ),
        ]
    )
    await db.flush()

    result = await WcsAdapterService(db, tenant_id).validate_point_mappings(
        warehouse,
        [
            {"location_barcode": "A-01-01", "point_code": "WCS-A-001"},
            {"location_barcode": "A-01-02", "point_code": "WCS-A-001"},
        ],
    )

    assert result["ok"] is False
    assert [issue["code"] for issue in result["issues"]] == ["duplicate_point_code"]


@pytest.mark.asyncio
async def test_wcs_point_mapping_import_and_export_include_unmapped_locations(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Import Tenant", code="WCI", contact_email="wci@example.com"))
    warehouse = Warehouse(id="wcs-wh-import", tenant_id=tenant_id, name="Dallas", code="DAL")
    db.add(warehouse)
    db.add(
        Zone(id="wcs-zone-import", tenant_id=tenant_id, warehouse_id="wcs-wh-import", name="A", code="A")
    )
    db.add_all(
        [
            Location(
                id="wcs-import-1",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-import",
                zone_id="wcs-zone-import",
                barcode="IMP-01",
                aisle="I",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                is_agv_accessible=True,
            ),
            Location(
                id="wcs-import-2",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-import",
                zone_id="wcs-zone-import",
                barcode="IMP-02",
                aisle="I",
                rack="01",
                level="01",
                position="02",
                location_type=LocationType.STORAGE.value,
                is_agv_accessible=True,
            ),
        ]
    )
    await db.flush()
    current_user = TokenPayload(
        sub="admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    validation = await validate_wcs_point_mappings(
        body=WcsPointMappingRequest(
            warehouse_id="wcs-wh-import",
            mappings=[
                WcsPointMapping(
                    location_barcode="IMP-01",
                    point_code="WCS-IMP-001",
                    point_type="storage",
                    point_name="Import 01",
                    buffer_code="A",
                    aisle_group="I01",
                    station_role="pickup_dropoff",
                    wcs_metadata={"layout_source": "test"},
                )
            ],
        ),
        current_user=current_user,
        db=db,
    )
    assert validation["ok"] is True
    assert validation["summary"]["unmapped_agv_accessible_locations"] == 1

    imported = await import_wcs_point_mappings(
        body=WcsPointMappingImportRequest(
            warehouse_id="wcs-wh-import",
            mappings=[
                WcsPointMapping(
                    location_barcode="IMP-01",
                    point_code="WCS-IMP-001",
                    point_type="storage",
                    point_name="Import 01",
                    buffer_code="A",
                    aisle_group="I01",
                    station_role="pickup_dropoff",
                    wcs_metadata={"layout_source": "test"},
                )
            ],
        ),
        current_user=current_user,
        db=db,
    )
    assert imported["status"] == "configured"
    assert imported["mapped_locations"] == 1

    exported = await list_wcs_point_mappings(
        warehouse_id="wcs-wh-import",
        include_unmapped=True,
        current_user=current_user,
        db=db,
    )
    assert exported["mapped_locations"] == 1
    assert exported["unmapped_locations"] == 1
    assert [item["point_code"] for item in exported["items"]] == ["WCS-IMP-001", None]
    assert exported["items"][0]["point_name"] == "Import 01"
    assert exported["items"][0]["station_role"] == "pickup_dropoff"
    assert exported["items"][0]["wcs_metadata"] == {"layout_source": "test"}
    mapped_location = await db.scalar(select(Location).where(Location.id == "wcs-import-1"))
    assert mapped_location.wcs_point_metadata["point_code"] == "WCS-IMP-001"


@pytest.mark.asyncio
async def test_wcs_adapter_blocks_putaway_to_dock_destination(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Dock Tenant", code="WCD", contact_email="wcd@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-dock",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                    "callback_url": "https://wms.example.test/callback",
                    "point_mappings": {
                        "wcs-source-dock": {"point_code": "SRC", "agv_reachable": True},
                        "wcs-dest-dock": {"point_code": "DOCK-DOOR-27", "agv_reachable": True},
                    },
                }
            },
        )
    )
    db.add(Zone(id="wcs-zone-dock", tenant_id=tenant_id, warehouse_id="wcs-wh-dock", name="Dock", code="D"))
    db.add_all(
        [
            Location(
                id="wcs-source-dock",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-dock",
                zone_id="wcs-zone-dock",
                barcode="SRC",
                aisle="A",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STORAGE.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
            Location(
                id="wcs-dest-dock",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-dock",
                zone_id="wcs-zone-dock",
                barcode="DOCK-DOOR-27",
                aisle="D",
                rack="27",
                level="01",
                position="01",
                location_type=LocationType.DOCK.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=True,
            ),
        ]
    )
    db.add(
        Task(
            id="wcs-task-dock",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-dock",
            task_type=TaskType.PUTAWAY.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            quantity=1,
            source_location_id="wcs-source-dock",
            destination_location_id="wcs-dest-dock",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()

    preview = await WcsAdapterService(db, tenant_id).preview_dispatch_task("wcs-task-dock")
    gate = preview["gate"]
    assert gate["ok"] is False
    assert gate["destination"]["point_type"] == LocationType.DOCK.value
    assert gate["issue_details"][-1]["code"] == "dock_destination_not_storage"
    assert [action["action"] for action in gate["issue_details"][-1]["recovery_actions"]] == [
        "choose_storage_destination",
        "change_task_type",
    ]

    with pytest.raises(Exception, match="Dock doors cannot be WCS storage destinations"):
        await WcsAdapterService(db, tenant_id).dispatch_task("wcs-task-dock")


@pytest.mark.asyncio
async def test_wcs_dispatch_gate_allows_buffer_and_agv_station_points(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="WCS External Point Tenant",
            code="WCE",
            contact_email="wce@example.com",
        )
    )
    db.add(
        Warehouse(
            id="wcs-wh-external",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                    "callback_url": "https://wms.example.test/callback",
                    "point_mappings": {
                        "wcs-buffer-source": {
                            "point_code": "BUF-01",
                            "point_type": "buffer",
                            "agv_reachable": True,
                        },
                        "wcs-station-dest": {
                            "point_code": "AGV-ST-01",
                            "point_type": "agv_station",
                            "agv_reachable": True,
                        },
                    },
                }
            },
        )
    )
    db.add(
        Zone(
            id="wcs-zone-external",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-external",
            name="External",
            code="E",
        )
    )
    db.add_all(
        [
            Location(
                id="wcs-buffer-source",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-external",
                zone_id="wcs-zone-external",
                barcode="BUF-01",
                aisle="B",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.BUFFER.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=False,
            ),
            Location(
                id="wcs-station-dest",
                tenant_id=tenant_id,
                warehouse_id="wcs-wh-external",
                zone_id="wcs-zone-external",
                barcode="AGV-ST-01",
                aisle="S",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.AGV_STATION.value,
                current_status=LocationStatus.AVAILABLE.value,
                is_agv_accessible=False,
            ),
        ]
    )
    db.add(
        Task(
            id="wcs-task-external",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-external",
            task_type=TaskType.MOVE.value,
            status=TaskStatus.PENDING.value,
            priority=5,
            quantity=1,
            source_location_id="wcs-buffer-source",
            destination_location_id="wcs-station-dest",
            assigned_type=AssignedType.UNASSIGNED.value,
        )
    )
    await db.flush()

    preview = await WcsAdapterService(db, tenant_id).preview_dispatch_task("wcs-task-external")

    assert preview["gate"]["ok"] is True
    assert preview["gate"]["issues"] == []
    assert preview["gate"]["issue_details"] == []
    assert preview["gate"]["source"]["point_type"] == LocationType.BUFFER.value
    assert preview["gate"]["destination"]["point_type"] == LocationType.AGV_STATION.value
    assert preview["planned_request"]["body"]["startPos"] == "BUF-01"
    assert preview["planned_request"]["body"]["endPos"] == "AGV-ST-01"


@pytest.mark.asyncio
async def test_wcs_adapter_maps_exception_callback_to_failed_task(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(Tenant(id=tenant_id, name="WCS Fail Tenant", code="WCF", contact_email="wcf@example.com"))
    db.add(Warehouse(id="wcs-wh-fail", tenant_id=tenant_id, name="Dallas", code="DAL"))
    db.add(
        Zone(
            id="wcs-zone-fail",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-fail",
            name="A",
            code="A",
        )
    )
    db.add(
        Location(
            id="wcs-source-fail",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-fail",
            zone_id="wcs-zone-fail",
            barcode="DOCK-FAIL",
            aisle="D",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        Task(
            id="wcs-task-fail",
            tenant_id=tenant_id,
            warehouse_id="wcs-wh-fail",
            task_type=TaskType.MOVE.value,
            status=TaskStatus.IN_PROGRESS.value,
            priority=5,
            quantity=1,
            source_location_id="wcs-source-fail",
            destination_location_id="wcs-source-fail",
            assigned_type=AssignedType.AGV.value,
            assigned_to="agv:wcs",
        )
    )
    db.add(
        WcsTaskBinding(
            tenant_id=tenant_id,
            task_id="wcs-task-fail",
            warehouse_id="wcs-wh-fail",
            wcs_task_id="5001",
            task_psn="PALLET-FAIL",
            start_pos="DOCK-FAIL",
            end_pos="DOCK-FAIL",
            status="in_progress",
        )
    )
    await db.flush()

    result = await WcsAdapterService(db, tenant_id).apply_task_callback(
        {
            "taskTid": 5001,
            "taskPsn": "PALLET-FAIL",
            "stepStatus": 40,
            "stepStatusName": "异常",
            "stepNote": "blocked at aisle",
            "stepAgvIp": "agv-02",
        }
    )
    task = await db.scalar(select(Task).where(Task.id == "wcs-task-fail"))
    binding = await db.scalar(select(WcsTaskBinding).where(WcsTaskBinding.task_id == "wcs-task-fail"))
    assert result["status"] == "failed"
    assert task.status == TaskStatus.FAILED.value
    assert task.failure_reason == "blocked at aisle"
    assert binding.failure_reason == "blocked at aisle"


@pytest.mark.asyncio
async def test_wcs_adapter_calls_ready_config_endpoint(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(Tenant(id=tenant_id, name="WCS Ready Tenant", code="WCR", contact_email="wcr@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-ready",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                }
            },
        )
    )
    await db.flush()

    captured: dict = {}

    async def fake_post_wcs(
        self,
        config: dict,
        path: str,
        payload: dict,
        *,
        failure_prefix: str,
    ) -> dict:
        captured["config"] = config
        captured["path"] = path
        captured["payload"] = payload
        captured["failure_prefix"] = failure_prefix
        return {"code": "0", "success": True, "msg": "ok"}

    monkeypatch.setattr(WcsAdapterService, "_post_wcs", fake_post_wcs)

    result = await WcsAdapterService(db, tenant_id).update_ready_config(
        "wcs-wh-ready",
        ready_sign="OUTBOUND-DOCK-A",
        api_sign=1,
        api_num=3,
    )

    assert result["success"] is True
    assert captured["config"]["base_url"] == "https://wcs.example.test"
    assert captured["path"] == "/task/wlReadyAgvRobot/editReadyConfig"
    assert captured["payload"] == {
        "wrarSign": "OUTBOUND-DOCK-A",
        "wrarApiSign": "1",
        "wrarApiNum": "3",
    }
    assert captured["failure_prefix"] == "WCS ready config update failed"


@pytest.mark.asyncio
async def test_wcs_adapter_calls_quality_complete_endpoint(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="WCS Quality Tenant",
            code="WCQ",
            contact_email="wcq@example.com",
        )
    )
    db.add(
        Warehouse(
            id="wcs-wh-quality",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                }
            },
        )
    )
    await db.flush()

    captured: dict = {}

    async def fake_post_wcs(
        self,
        config: dict,
        path: str,
        payload: dict,
        *,
        failure_prefix: str,
    ) -> dict:
        captured["config"] = config
        captured["path"] = path
        captured["payload"] = payload
        captured["failure_prefix"] = failure_prefix
        return {"code": "0", "success": True, "data": None}

    monkeypatch.setattr(WcsAdapterService, "_post_wcs", fake_post_wcs)

    result = await WcsAdapterService(db, tenant_id).complete_quality(
        "wcs-wh-quality",
        wtaskstep_tid="4121",
        wtaskinfo_psn="PALLET-QC-001",
        quality_status="不合格",
        unqualified_buffer="QC-NG-01",
        params={"inspector": "u-1"},
    )

    assert result["success"] is True
    assert captured["config"]["access_token"] == "token-1"
    assert captured["path"] == "/QualityComplete"
    assert captured["payload"] == {
        "wtaskstepTid": "4121",
        "wtaskinfoPsn": "PALLET-QC-001",
        "qualityStatus": "不合格",
        "unqualifiedBuffer": "QC-NG-01",
        "params": {"inspector": "u-1"},
    }
    assert captured["failure_prefix"] == "WCS quality completion failed"


@pytest.mark.asyncio
async def test_wcs_adapter_previews_ready_config_without_external_call(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(Tenant(id=tenant_id, name="WCS Preview Tenant", code="WCP", contact_email="wcp@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-ready-preview",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                    "callback_url": "https://api.example.test/api/v1/integrations/wcs/webhook/t/taskfinish",
                }
            },
        )
    )
    await db.flush()

    async def fail_post_wcs(*args, **kwargs):
        raise AssertionError("preview_ready_config must not call WCS")

    monkeypatch.setattr(WcsAdapterService, "_post_wcs", fail_post_wcs)

    result = await WcsAdapterService(db, tenant_id).preview_ready_config(
        "wcs-wh-ready-preview",
        ready_sign="OUTBOUND-DOCK-A",
        api_sign=1,
        api_num=3,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["writes"] is False
    assert result["planned_request"]["endpoint"] == "/task/wlReadyAgvRobot/editReadyConfig"
    assert result["planned_request"]["body"] == {
        "wrarSign": "OUTBOUND-DOCK-A",
        "wrarApiSign": "1",
        "wrarApiNum": "3",
    }
    assert result["planned_request"]["wcs_config"]["access_token"] == "***redacted***"


@pytest.mark.asyncio
async def test_wcs_adapter_previews_quality_complete_without_external_call(
    db: AsyncSession,
    tenant_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(Tenant(id=tenant_id, name="WCS Quality Preview", code="WCQP", contact_email="wcqp@example.com"))
    db.add(
        Warehouse(
            id="wcs-wh-quality-preview",
            tenant_id=tenant_id,
            name="Dallas",
            code="DAL",
            address={
                "_wcs": {
                    "base_url": "https://wcs.example.test",
                    "access_token": "token-1",
                }
            },
        )
    )
    await db.flush()

    async def fail_post_wcs(*args, **kwargs):
        raise AssertionError("preview_quality_complete must not call WCS")

    monkeypatch.setattr(WcsAdapterService, "_post_wcs", fail_post_wcs)

    result = await WcsAdapterService(db, tenant_id).preview_quality_complete(
        "wcs-wh-quality-preview",
        wtaskinfo_psn="PALLET-QC-001",
        quality_status="合格",
        params={"inspector": "u-1"},
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["writes"] is False
    assert result["planned_request"]["endpoint"] == "/QualityComplete"
    assert result["planned_request"]["body"] == {
        "wtaskinfoPsn": "PALLET-QC-001",
        "qualityStatus": "合格",
        "params": {"inspector": "u-1"},
    }
