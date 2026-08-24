"""Regression tests: receiving (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.order_details import get_inbound_detail
from app.api.v1.endpoints.receiving import list_receiving_labels
from app.api.v1.endpoints.tenants import (
    ReceivingCodeRuleSettings,
    ReceivingLabelTemplateSettings,
    get_current_receiving_code_rules,
    get_current_receiving_label_template,
    update_current_receiving_code_rules,
    update_current_receiving_label_template,
)
from app.core.security import TokenPayload, UserRole
from app.models.agent_evidence import AgentEvidence
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction, TransactionType
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundOrderLine,
    InboundPackage,
    InboundPackageStatus,
    ReceivingLabel,
    ReceivingObservedCode,
)
from app.models.task import Task, TaskType
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.receiving_service import ReceivingService


@pytest.mark.asyncio
async def test_receiving_code_rules_endpoint_persists_tenant_settings(
    db: AsyncSession, tenant_id: str
):
    db.add(Tenant(id=tenant_id, name="Test Tenant", code="TST", contact_email="tenant@example.com"))
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-tenant-admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="tenant-admin@example.com",
        exp=datetime.now(UTC),
    )

    updated = await update_current_receiving_code_rules(
        ReceivingCodeRuleSettings(
            prefix="HU",
            separator="_",
            include_order_number=False,
            sequence_padding=4,
            uppercase=False,
        ),
        current_user=tenant_admin,
        db=db,
    )

    fetched = await get_current_receiving_code_rules(current_user=tenant_admin, db=db)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()

    assert updated.prefix == "HU"
    assert updated.separator == "_"
    assert updated.include_order_number is False
    assert updated.sequence_padding == 4
    assert updated.uppercase is False
    assert updated.sample_code == "HU_0001"
    assert fetched.sample_code == "HU_0001"
    assert tenant.settings["receiving_code_rules"]["prefix"] == "HU"
    assert tenant.settings["receiving_code_rules"]["sequence_padding"] == 4


@pytest.mark.asyncio
async def test_receiving_service_builds_label_code_from_tenant_rules(
    db: AsyncSession, tenant_id: str
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Rule Tenant",
            code="RULE",
            contact_email="rules@example.com",
            settings={
                "receiving_code_rules": {
                    "prefix": "hu",
                    "separator": "",
                    "include_order_number": False,
                    "sequence_padding": 5,
                    "uppercase": True,
                }
            },
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    rules = await service._get_receiving_code_rules()
    code = service._build_label_code("INB-2401", 7, rules)

    assert rules["prefix"] == "hu"
    assert rules["separator"] == ""
    assert rules["include_order_number"] is False
    assert rules["sequence_padding"] == 5
    assert rules["uppercase"] is True
    assert code == "HU00007"


@pytest.mark.asyncio
async def test_receiving_label_template_endpoint_accepts_package_fields(
    db: AsyncSession, tenant_id: str
):
    db.add(
        Tenant(id=tenant_id, name="Template Tenant", code="TMPL", contact_email="tmpl@example.com")
    )
    await db.flush()

    tenant_admin = TokenPayload(
        sub="user-template-admin",
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN.value,
        email="template-admin@example.com",
        exp=datetime.now(UTC),
    )

    updated = await update_current_receiving_label_template(
        ReceivingLabelTemplateSettings(
            fields=[
                "order_number",
                "package_number",
                "package_type",
                "sku_code",
                "tracking_number",
            ],
            show_field_labels=True,
        ),
        current_user=tenant_admin,
        db=db,
    )
    fetched = await get_current_receiving_label_template(current_user=tenant_admin, db=db)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()

    assert "package_number" in fetched.available_fields
    assert "package_type" in fetched.available_fields
    assert updated.fields == [
        "order_number",
        "package_number",
        "package_type",
        "sku_code",
        "tracking_number",
    ]
    assert fetched.fields == updated.fields
    assert tenant.settings["receiving_label_template"]["fields"][1:3] == [
        "package_number",
        "package_type",
    ]


@pytest.mark.asyncio
async def test_receiving_labels_expose_package_context_for_printing(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Print Tenant", code="PRT", contact_email="print@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-print-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-print-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-PRINT-1",
            name="Print Test",
        )
    )
    db.add(
        Location(
            id="staging-print-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-print-1",
            barcode="STAGE-PRINT-01",
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
        order_number="ASN-PRINT-1",
        lines=[{"sku_id": "sku-print-1", "quantity": 4}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None

    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=4,
        package_type="crate",
        external_tracking_number="PRINT-TRACK-1",
    )
    await service.receive_package(
        order_id=order.id,
        package_id=package.id,
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-print-1",
        package_count=2,
        pallet_count=1,
        measured_weight_kg=8.5,
        receiving_note="Package print verification",
        user_id=user_id,
    )

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    labels = await list_receiving_labels(order.id, current_user=current_user, db=db)

    assert len(labels) == 1
    assert labels[0]["package_number"] == 1
    assert labels[0]["package_type"] == "crate"
    assert labels[0]["package_count"] == 2
    assert labels[0]["pallet_count"] == 1
    assert labels[0]["measured_weight_kg"] == 8.5
    assert labels[0]["receiving_note"] == "Package print verification"


@pytest.mark.asyncio
async def test_receive_package_preview_returns_confirmation_without_mutation(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Preview Tenant", code="PRV", contact_email="prv@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Preview Client", code="PRV"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Preview WH", code="PWH"))
    db.add(
        Zone(
            id="zone-receive-preview",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-receive-preview",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-receive-preview",
            barcode="DOCK-PREVIEW-01",
            aisle="D",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-receive-preview",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-PREVIEW",
            name="Preview SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-PREVIEW",
        lines=[{"sku_id": "sku-receive-preview", "quantity": 6}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None
    package = await service.create_package(order_id=order.id, line_id=line.id, expected_qty=6)

    preview = await service.preview_package_receipt(
        order_id=order.id,
        package_id=package.id,
        quantity_received=5,
        quantity_damaged=1,
        staging_location_id="staging-receive-preview",
        package_count=1,
        receiving_note="Preview only",
    )

    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["action"] == "receiving.confirm"
    assert preview["state_before"]["package_status"] == InboundPackageStatus.EXPECTED.value
    assert preview["state_after"]["package_status"] == InboundPackageStatus.STAGED.value
    assert preview["state_after"]["inventory_delta"] == 4
    assert preview["confirmation_payload"]["records"][0]["discrepancy"] == -1
    confirmation_token = preview["confirmation_payload"]["confirmation_token"]
    assert confirmation_token.startswith("rcv-confirm:")
    assert preview["confirmation_payload"]["payload_hash"]
    assert preview["evidence_id"]
    assert preview["confirmation_payload"]["evidence_id"] == preview["evidence_id"]
    assert preview["planned_request"]["endpoint"].endswith(f"/packages/{package.id}/receive")

    stored_package = await db.scalar(select(InboundPackage).where(InboundPackage.id == package.id))
    assert stored_package is not None
    assert stored_package.status == InboundPackageStatus.EXPECTED.value
    assert stored_package.received_qty == 0
    assert stored_package.damaged_qty == 0
    assert stored_package.staging_location_id is None
    inventory_rows = (
        await db.execute(select(Inventory).where(Inventory.tenant_id == tenant_id))
    ).scalars().all()
    transactions = (
        await db.execute(
            select(InventoryTransaction).where(InventoryTransaction.tenant_id == tenant_id)
        )
    ).scalars().all()
    assert inventory_rows == []
    assert transactions == []
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    assert evidence is not None
    assert evidence.status == "previewed"
    assert evidence.payload_hash == preview["confirmation_payload"]["payload_hash"]
    assert evidence.confirmation_token_hash != confirmation_token

    confirmed = await service.confirm_package_receipt_with_token(
        order_id=order.id,
        package_id=package.id,
        confirmation_token=confirmation_token,
        quantity_received=5,
        quantity_damaged=1,
        staging_location_id="staging-receive-preview",
        package_count=1,
        receiving_note="Preview only",
        idempotency_key="confirm-preview-test",
    )
    assert confirmed["ok"] is True
    assert confirmed["dry_run"] is False
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "confirm-preview-test"
    assert evidence.confirmed_at is not None

    inventory_rows = (
        await db.execute(select(Inventory).where(Inventory.tenant_id == tenant_id))
    ).scalars().all()
    assert len(inventory_rows) == 1
    assert inventory_rows[0].quantity_on_hand == 4


@pytest.mark.asyncio
async def test_receiving_scan_and_dock_previews_do_not_mutate(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(Tenant(id=tenant_id, name="Scan Preview Tenant", code="SPV", contact_email="spv@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Scan Preview Client", code="SPV"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Scan Preview WH", code="SPW"))
    db.add(
        Zone(
            id="zone-scan-preview",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-scan-preview",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-scan-preview",
            barcode="DOCK-SCAN-01",
            aisle="D",
            rack="02",
            level="01",
            position="01",
            location_type=LocationType.STAGING.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-scan-preview",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-SCAN-PREVIEW",
            name="Scan Preview SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-SCAN-PREVIEW",
        lines=[
            {
                "sku_id": "sku-scan-preview",
                "quantity": 4,
                "packages": [
                    {
                        "expected_qty": 4,
                        "package_type": "carton",
                        "external_tracking_number": "TRK-SCAN-PREVIEW",
                    }
                ],
            }
        ],
    )
    await service.start_receiving(order.id)
    package = await db.scalar(select(InboundPackage).where(InboundPackage.order_id == order.id))
    assert package is not None

    scan_preview = await service.preview_scan_label(order.id, "TRK-SCAN-PREVIEW")
    dock_preview = await service.preview_choose_dock(
        order_id=order.id,
        package_id=package.id,
        staging_location_id="staging-scan-preview",
    )
    recovery_preview = ReceivingService.preview_recovery("staging_location_required")

    assert scan_preview["ok"] is True
    assert scan_preview["dry_run"] is True
    assert scan_preview["result"]["package_id"] == package.id
    assert dock_preview["ok"] is True
    assert dock_preview["state_after"]["staging_location_id"] == "staging-scan-preview"
    assert recovery_preview["next_action"] == "choose_dock"

    observed_codes = (
        await db.execute(
            select(ReceivingObservedCode).where(ReceivingObservedCode.tenant_id == tenant_id)
        )
    ).scalars().all()
    stored_package = await db.scalar(select(InboundPackage).where(InboundPackage.id == package.id))
    assert observed_codes == []
    assert stored_package is not None
    assert stored_package.staging_location_id is None
    assert stored_package.status == InboundPackageStatus.EXPECTED.value


@pytest.mark.asyncio
async def test_correct_staged_package_receipt_updates_inventory_with_adjustment(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(id=tenant_id, name="Correction Tenant", code="COR", contact_email="cor@example.com")
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-correct-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-correct-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-correct-1",
            barcode="STAGE-CORRECT-01",
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
            id="sku-correct-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-COR-1",
            name="Correction SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-CORRECT-1",
        lines=[{"sku_id": "sku-correct-1", "quantity": 4}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=4,
        package_type="crate",
        external_tracking_number="TRK-COR-1",
    )
    await service.receive_package(
        order_id=order.id,
        package_id=package.id,
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-correct-1",
        user_id=user_id,
    )

    result = await service.correct_package_receipt(
        order_id=order.id,
        package_id=package.id,
        quantity_received=3,
        quantity_damaged=0,
        staging_location_id="staging-correct-1",
        measured_weight_kg=12.5,
        receiving_note="Corrected count at dock",
        external_tracking_number="TRK-COR-UPDATED",
        user_id=user_id,
    )

    inv = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.location_id == "staging-correct-1",
            Inventory.sku_id == "sku-correct-1",
        )
    )
    transactions = (
        (
            await db.execute(
                select(InventoryTransaction)
                .where(InventoryTransaction.reference_id == order.id)
                .order_by(InventoryTransaction.performed_at.asc())
            )
        )
        .scalars()
        .all()
    )
    label = await db.scalar(
        select(ReceivingLabel).where(ReceivingLabel.inbound_package_id == package.id)
    )
    handling_unit = await db.scalar(
        select(HandlingUnit).where(HandlingUnit.inbound_package_id == package.id)
    )
    refreshed_line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.id == line.id))

    assert result["received_qty"] == 3
    assert result["external_tracking_number"] == "TRK-COR-UPDATED"
    assert inv.quantity_on_hand == 3
    assert [txn.quantity_change for txn in transactions] == [4, -1]
    assert transactions[-1].transaction_type == TransactionType.ADJUST.value
    assert label.received_qty == 3
    assert label.external_tracking_number == "TRK-COR-UPDATED"
    assert handling_unit.received_qty == 3
    assert float(handling_unit.measured_weight_kg) == 12.5
    assert refreshed_line.quantity_received == 3
    assert refreshed_line.receiving_note == "Corrected count at dock"


@pytest.mark.asyncio
async def test_correct_staged_package_to_all_damaged_clears_staging_inventory(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Damaged Correction Tenant",
            code="DMG",
            contact_email="dmg@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-damaged-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-damaged-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-damaged-1",
            barcode="STAGE-DAMAGED-01",
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
            id="sku-damaged-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-DMG-1",
            name="Damaged SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-DAMAGED-1",
        lines=[{"sku_id": "sku-damaged-1", "quantity": 3}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=3,
        package_type="carton",
    )
    await service.receive_package(
        order_id=order.id,
        package_id=package.id,
        quantity_received=3,
        quantity_damaged=0,
        staging_location_id="staging-damaged-1",
        user_id=user_id,
    )

    result = await service.correct_package_receipt(
        order_id=order.id,
        package_id=package.id,
        quantity_received=2,
        quantity_damaged=2,
        user_id=user_id,
    )

    inv = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.location_id == "staging-damaged-1",
            Inventory.sku_id == "sku-damaged-1",
        )
    )
    handling_unit = await db.scalar(
        select(HandlingUnit).where(HandlingUnit.inbound_package_id == package.id)
    )
    refreshed_line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.id == line.id))

    assert result["status"] == InboundPackageStatus.RECEIVED.value
    assert result["staging_location_id"] is None
    assert inv.quantity_on_hand == 0
    assert handling_unit.staging_location_id is None
    assert handling_unit.status == "received"
    assert refreshed_line.quantity_received == 2
    assert refreshed_line.quantity_damaged == 2


@pytest.mark.asyncio
async def test_putaway_pending_package_correction_rejects_quantity_change(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Limited Correction Tenant",
            code="LIM",
            contact_email="lim@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Danube Foods", code="DAN"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Budapest", code="BUD"))
    db.add(
        Zone(
            id="zone-limited-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-limited-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-limited-1",
            barcode="STAGE-LIMITED-01",
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
            id="sku-limited-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-LIM-1",
            name="Limited SKU",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-LIMITED-1",
        lines=[{"sku_id": "sku-limited-1", "quantity": 2}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=2,
        package_type="crate",
    )
    await service.receive_package(
        order_id=order.id,
        package_id=package.id,
        quantity_received=2,
        quantity_damaged=0,
        staging_location_id="staging-limited-1",
        user_id=user_id,
    )
    package.status = InboundPackageStatus.PUTAWAY_PENDING.value
    await db.flush()

    metadata_result = await service.correct_package_receipt(
        order_id=order.id,
        package_id=package.id,
        quantity_received=2,
        quantity_damaged=0,
        staging_location_id="staging-limited-1",
        measured_weight_kg=9.25,
        receiving_note="Metadata correction only",
        external_carton_mark="CARTON-LIMITED",
        user_id=user_id,
    )

    assert metadata_result["status"] == InboundPackageStatus.PUTAWAY_PENDING.value
    assert float(package.measured_weight_kg) == 9.25
    assert package.external_carton_mark == "CARTON-LIMITED"

    metadata_without_operational_fields = await service.correct_package_receipt(
        order_id=order.id,
        package_id=package.id,
        quantity_received=2,
        quantity_damaged=0,
        measured_length_cm=42.5,
        user_id=user_id,
    )

    assert (
        metadata_without_operational_fields["status"] == InboundPackageStatus.PUTAWAY_PENDING.value
    )
    assert metadata_without_operational_fields["staging_location_id"] == "staging-limited-1"
    assert float(package.measured_length_cm) == 42.5

    with pytest.raises(HTTPException) as rent_free_exc_info:
        await service.correct_package_receipt(
            order_id=order.id,
            package_id=package.id,
            quantity_received=2,
            quantity_damaged=0,
            staging_location_id="staging-limited-1",
            rent_free_days=5,
            user_id=user_id,
        )

    assert rent_free_exc_info.value.status_code == 409

    with pytest.raises(HTTPException) as exc_info:
        await service.correct_package_receipt(
            order_id=order.id,
            package_id=package.id,
            quantity_received=1,
            quantity_damaged=0,
            staging_location_id="staging-limited-1",
            user_id=user_id,
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_start_receiving_rejects_cross_tenant_order_access(
    db: AsyncSession,
):
    """A tenant must not be able to start receiving another tenant's order."""
    tenant_a = "tenant-a-001"
    client_a = "client-a-001"
    warehouse_a = "warehouse-a-001"
    tenant_b = "tenant-b-001"
    client_b = "client-b-001"
    warehouse_b = "warehouse-b-001"

    db.add(Tenant(id=tenant_a, name="Tenant A", code="TNA", contact_email="a@example.com"))
    db.add(Client(id=client_a, tenant_id=tenant_a, name="Client A", code="CLA"))
    db.add(Warehouse(id=warehouse_a, tenant_id=tenant_a, name="Warehouse A", code="WHA"))

    db.add(Tenant(id=tenant_b, name="Tenant B", code="TNB", contact_email="b@example.com"))
    db.add(Client(id=client_b, tenant_id=tenant_b, name="Client B", code="CLB"))
    db.add(Warehouse(id=warehouse_b, tenant_id=tenant_b, name="Warehouse B", code="WHB"))
    db.add(
        InboundOrder(
            id="inbound-b-1",
            tenant_id=tenant_b,
            client_id=client_b,
            warehouse_id=warehouse_b,
            order_number="INB-B-001",
            status="expected",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_a)
    with pytest.raises(HTTPException) as exc:
        await service.start_receiving("inbound-b-1")

    assert exc.value.status_code == 404

    untouched_order = await db.scalar(select(InboundOrder).where(InboundOrder.id == "inbound-b-1"))
    assert untouched_order is not None
    assert untouched_order.status == "expected"


@pytest.mark.asyncio
async def test_create_inbound_order_delays_receiving_labels_until_confirm(
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
        SKU(
            id="sku-rcv-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OIL-006",
            name="Oil",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-FLOUR-20",
            name="Flour",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-889",
        lines=[
            {"sku_id": "sku-rcv-1", "quantity": 12},
            {"sku_id": "sku-rcv-2", "quantity": 8},
        ],
    )

    labels = (
        (
            await db.execute(
                select(ReceivingLabel)
                .where(ReceivingLabel.order_id == order.id)
                .order_by(ReceivingLabel.label_code.asc())
            )
        )
        .scalars()
        .all()
    )

    lines = (
        (
            await db.execute(
                select(InboundOrderLine)
                .where(InboundOrderLine.order_id == order.id)
                .order_by(InboundOrderLine.line_number.asc())
            )
        )
        .scalars()
        .all()
    )

    assert labels == []
    assert len(lines) == 2
    assert lines[0].line_number == 1
    assert lines[1].line_number == 2
    assert service._build_label_code(order.order_number, lines[0].line_number) == "RCV-ASN-889-001"
    assert service._build_label_code(order.order_number, lines[1].line_number) == "RCV-ASN-889-002"


@pytest.mark.asyncio
async def test_create_inbound_order_accepts_upstream_package_breakdown(
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
        SKU(
            id="sku-pkg-upstream",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-PKG-001",
            name="Package Aware",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-PKG-UPSTREAM-1",
        lines=[
            {
                "line_number": 7,
                "sku_id": "sku-pkg-upstream",
                "quantity": 6,
                "packages": [
                    {
                        "package_number": 2,
                        "expected_qty": 2,
                        "package_type": "carton",
                        "external_tracking_number": "TRACK-UP-2",
                    },
                    {
                        "package_number": 5,
                        "expected_qty": 4,
                        "package_type": "crate",
                        "external_carton_mark": "CRT-UP-5",
                    },
                ],
            }
        ],
    )

    line = await db.scalar(
        select(InboundOrderLine).where(
            InboundOrderLine.order_id == order.id,
            InboundOrderLine.sku_id == "sku-pkg-upstream",
        )
    )
    packages = (
        (
            await db.execute(
                select(InboundPackage)
                .where(InboundPackage.order_id == order.id)
                .order_by(InboundPackage.package_number.asc())
            )
        )
        .scalars()
        .all()
    )
    labels = (
        (await db.execute(select(ReceivingLabel).where(ReceivingLabel.order_id == order.id)))
        .scalars()
        .all()
    )

    assert line is not None
    assert line.line_number == 7
    assert line.quantity_expected == 6
    assert [package.package_number for package in packages] == [2, 5]
    assert [package.expected_qty for package in packages] == [2, 4]
    assert [package.package_type for package in packages] == ["carton", "crate"]
    assert packages[0].external_tracking_number == "TRACK-UP-2"
    assert packages[1].external_carton_mark == "CRT-UP-5"
    assert labels == []


@pytest.mark.asyncio
async def test_receiving_label_supports_external_scan_codes(
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
        SKU(
            id="sku-rcv-ext-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OIL-006",
            name="Oil",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-EXT-001",
        lines=[
            {
                "sku_id": "sku-rcv-ext-1",
                "quantity": 6,
                "external_tracking_number": "TRK-001",
                "external_carton_mark": "CTN-001",
                "external_customer_barcode": "CUS-001",
            }
        ],
    )
    await service.start_receiving(order.id)

    tracking_match = await service.scan_label(order.id, "TRK-001")
    carton_match = await service.scan_label(order.id, "CTN-001")
    customer_match = await service.scan_label(order.id, "CUS-001")

    assert tracking_match["label_code"] == "RCV-ASN-EXT-001-001"
    assert tracking_match["matched_by"] == "external_tracking_number"
    assert carton_match["matched_by"] == "external_carton_mark"
    assert customer_match["matched_by"] == "external_customer_barcode"


@pytest.mark.asyncio
async def test_receive_label_accepts_external_scan_code(
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
            id="zone-rcv-ext-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-ext-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-FLOUR-20",
            name="Flour",
        )
    )
    db.add(
        Location(
            id="staging-ext-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-rcv-ext-1",
            barcode="STAGE-EXT-01",
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
        order_number="ASN-EXT-002",
        lines=[
            {
                "sku_id": "sku-rcv-ext-2",
                "quantity": 5,
                "external_carton_mark": "CTN-EXT-002",
            }
        ],
    )
    await service.start_receiving(order.id)

    receipt = await service.receive_label(
        order_id=order.id,
        label_code="CTN-EXT-002",
        quantity_received=5,
        quantity_damaged=1,
        staging_location_id="staging-ext-1",
        user_id=user_id,
    )

    assert receipt["label_code"] == "RCV-ASN-EXT-002-001"
    assert receipt["matched_by"] == "external_carton_mark"
    assert receipt["received"] == 5
    assert receipt["damaged"] == 1


@pytest.mark.asyncio
async def test_single_line_multiple_packages_generate_multiple_internal_labels_and_putaway_tasks(
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
            id="zone-pkg-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-pkg-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-PKG-1",
            name="Package Split",
        )
    )
    db.add_all(
        [
            Location(
                id="staging-pkg-1",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-pkg-1",
                barcode="STAGE-PKG-01",
                aisle="STAGE",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
            Location(
                id="staging-pkg-2",
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                zone_id="zone-pkg-1",
                barcode="STAGE-PKG-02",
                aisle="STAGE",
                rack="01",
                level="01",
                position="02",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
            ),
        ]
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-PKG-001",
        lines=[{"sku_id": "sku-rcv-pkg-1", "quantity": 10}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None

    package_one = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=6,
        external_tracking_number="PKG-TRACK-001",
    )
    package_two = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=4,
        external_carton_mark="PKG-CARTON-002",
    )

    first_scan = await service.scan_label(order.id, "PKG-TRACK-001")
    second_scan = await service.scan_label(order.id, "PKG-CARTON-002")

    assert first_scan["package_id"] == package_one.id
    assert second_scan["package_id"] == package_two.id

    await service.receive_package(
        order_id=order.id,
        package_id=package_one.id,
        quantity_received=6,
        quantity_damaged=0,
        staging_location_id="staging-pkg-1",
        user_id=user_id,
    )
    await service.receive_package(
        order_id=order.id,
        package_id=package_two.id,
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-pkg-2",
        user_id=user_id,
    )

    labels = (
        (
            await db.execute(
                select(ReceivingLabel)
                .where(ReceivingLabel.order_id == order.id)
                .order_by(ReceivingLabel.label_code.asc())
            )
        )
        .scalars()
        .all()
    )
    handling_units = (
        (
            await db.execute(
                select(HandlingUnit)
                .where(HandlingUnit.order_id == order.id)
                .order_by(HandlingUnit.unit_code.asc())
            )
        )
        .scalars()
        .all()
    )

    assert len(labels) == 2
    assert {label.inbound_package_id for label in labels} == {package_one.id, package_two.id}
    assert len(handling_units) == 2
    assert {unit.inbound_package_id for unit in handling_units} == {package_one.id, package_two.id}

    refreshed_line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.id == line.id))
    assert refreshed_line is not None
    assert refreshed_line.quantity_received == 10
    assert refreshed_line.quantity_damaged == 0

    completion = await service.complete_receiving(order.id, user_id=user_id)
    assert completion["created_tasks"] == 2

    tasks = (
        (
            await db.execute(
                select(Task)
                .where(
                    Task.tenant_id == tenant_id,
                    Task.reference_type == "inbound_order",
                    Task.reference_id == order.id,
                    Task.task_type == TaskType.PUTAWAY.value,
                )
                .order_by(Task.handling_unit_id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks) == 2
    assert {task.source_location_id for task in tasks} == {"staging-pkg-1", "staging-pkg-2"}
    assert {task.handling_unit_id for task in tasks} == {unit.id for unit in handling_units}

    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        permissions=["*"],
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    detail = await get_inbound_detail(order.id, current_user=current_user, db=db)
    assert len(detail["lines"]) == 1
    assert len(detail["lines"][0]["packages"]) == 2
    assert {pkg["package_number"] for pkg in detail["lines"][0]["packages"]} == {1, 2}
    assert {pkg["status"] for pkg in detail["lines"][0]["packages"]} == {"putaway_pending"}
    assert {
        pkg["receiving_labels"][0]["label_code"]
        for pkg in detail["lines"][0]["packages"]
        if pkg["receiving_labels"]
    } == {label.label_code for label in labels}
    assert {
        pkg["handling_units"][0]["unit_code"]
        for pkg in detail["lines"][0]["packages"]
        if pkg["handling_units"]
    } == {unit.unit_code for unit in handling_units}
    assert {
        pkg["downstream_tasks"][0]["id"]
        for pkg in detail["lines"][0]["packages"]
        if pkg["downstream_tasks"]
    } == {task.id for task in tasks}


@pytest.mark.asyncio
async def test_observed_code_can_resolve_back_to_the_same_package(
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
        SKU(
            id="sku-rcv-obs-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OBS-1",
            name="Observed Codes",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-OBS-001",
        lines=[{"sku_id": "sku-rcv-obs-1", "quantity": 5}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None
    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=5,
        external_tracking_number="OBS-TRACK-001",
    )

    scan = await service.scan_label(order.id, "OBS-TRACK-001")
    assert scan["package_id"] == package.id
    added_code = await service.add_observed_code(
        order_id=order.id,
        label_code=scan["label_code"],
        code_value="OBS-CARTON-001",
        code_type="carton_mark",
        source="manual",
        is_primary=False,
    )
    assert added_code.inbound_package_id == package.id

    scan_again = await service.scan_label(order.id, "OBS-CARTON-001")
    assert scan_again["package_id"] == package.id
    assert scan_again["matched_by"] == "external_carton_mark"


@pytest.mark.asyncio
async def test_open_package_without_external_codes_allows_package_level_code_capture(
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
        SKU(
            id="sku-rcv-open-pkg",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OPEN-01",
            name="Open Package",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-OPEN-PKG-001",
        lines=[{"sku_id": "sku-rcv-open-pkg", "quantity": 3}],
    )
    await service.start_receiving(order.id)
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None

    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=3,
        package_type="crate",
    )
    opened = await service.open_package(order.id, package.id)

    assert opened["package_id"] == package.id
    assert opened["package_number"] == 1
    assert opened["label_type"] == "crate"
    assert opened["opened_directly"] is True

    added = await service.add_observed_code(
        order_id=order.id,
        label_code=None,
        package_id=package.id,
        code_value="MANUAL-CODE-001",
        code_type="customer_barcode",
        source="manual",
        is_primary=True,
    )
    listed = await service.list_observed_codes(order_id=order.id, package_id=package.id)

    assert added.inbound_package_id == package.id
    assert len(listed) == 1
    assert listed[0].code_value == "MANUAL-CODE-001"


@pytest.mark.asyncio
async def test_packages_can_be_updated_and_deleted_before_receipt_confirmation(
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
        SKU(
            id="sku-rcv-edit-pkg",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-EDIT-01",
            name="Editable Package",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-EDIT-PKG-001",
        lines=[{"sku_id": "sku-rcv-edit-pkg", "quantity": 8}],
    )
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.order_id == order.id))
    assert line is not None

    package = await service.create_package(
        order_id=order.id,
        line_id=line.id,
        expected_qty=5,
        external_tracking_number="EDIT-TRACK-001",
    )
    updated = await service.update_package(
        order_id=order.id,
        package_id=package.id,
        expected_qty=6,
        package_type="pallet",
        external_tracking_number="EDIT-TRACK-002",
        external_carton_mark="EDIT-CARTON-002",
    )

    assert updated.expected_qty == 6
    assert updated.package_type == "pallet"
    assert updated.external_tracking_number == "EDIT-TRACK-002"
    assert updated.external_carton_mark == "EDIT-CARTON-002"

    await service.delete_package(order.id, package.id)
    deleted = await db.scalar(select(InboundPackage).where(InboundPackage.id == package.id))
    assert deleted is None


@pytest.mark.asyncio
async def test_receiving_observed_codes_are_editable_before_confirm_and_persist_after_confirm(
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
            id="zone-rcv-codes-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-codes-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-CODE-01",
            name="Code Item",
        )
    )
    db.add(
        Location(
            id="staging-codes-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-rcv-codes-1",
            barcode="STAGE-CODE-01",
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
        order_number="ASN-CODES-001",
        lines=[
            {
                "sku_id": "sku-rcv-codes-1",
                "quantity": 4,
                "external_tracking_number": "TRK-CODES-1",
            }
        ],
    )
    await service.start_receiving(order.id)

    scan = await service.scan_label(order.id, "TRK-CODES-1", source="scan")
    assert scan["captured_codes"][0]["code_value"] == "TRK-CODES-1"
    assert scan["captured_codes"][0]["code_type"] == "tracking_number"

    manual = await service.add_observed_code(
        order_id=order.id,
        label_code=scan["label_code"],
        code_value="BOX-SECONDARY-1",
        code_type="carton_mark",
        source="manual",
        is_primary=False,
    )
    await service.update_observed_code(
        order_id=order.id,
        code_id=manual.id,
        code_value="BOX-SECONDARY-2",
        code_type="carton_mark",
        is_primary=False,
    )

    observed_before = await service.list_observed_codes(order.id, scan["label_code"])
    assert [code.code_value for code in observed_before] == ["TRK-CODES-1", "BOX-SECONDARY-2"]
    assert all(code.is_confirmed is False for code in observed_before)

    receipt = await service.receive_label(
        order_id=order.id,
        label_code="TRK-CODES-1",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-codes-1",
        user_id=user_id,
    )

    observed_after = (
        (
            await db.execute(
                select(ReceivingObservedCode).where(
                    ReceivingObservedCode.tenant_id == tenant_id,
                    ReceivingObservedCode.order_id == order.id,
                )
            )
        )
        .scalars()
        .all()
    )
    handling_unit = (
        await db.execute(
            select(HandlingUnit).where(
                HandlingUnit.tenant_id == tenant_id,
                HandlingUnit.order_id == order.id,
            )
        )
    ).scalar_one()

    assert len(receipt["captured_codes"]) == 2
    assert all(code.is_confirmed is True for code in observed_after)
    assert {code.code_value for code in observed_after} == {"TRK-CODES-1", "BOX-SECONDARY-2"}
    assert handling_unit.external_tracking_number == "TRK-CODES-1"
    assert handling_unit.external_carton_mark == "BOX-SECONDARY-2"


@pytest.mark.asyncio
async def test_scan_label_rejects_ambiguous_external_code(
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
        SKU(
            id="sku-rcv-ext-3",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-SOUP-01",
            name="Soup",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-ext-4",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-PASTA-01",
            name="Pasta",
        )
    )
    await db.flush()

    service = ReceivingService(db, tenant_id)
    order = await service.create_inbound_order(
        client_id=client_id,
        warehouse_id=warehouse_id,
        order_number="ASN-EXT-003",
        lines=[
            {"sku_id": "sku-rcv-ext-3", "quantity": 3, "external_tracking_number": "TRK-DUP-1"},
            {"sku_id": "sku-rcv-ext-4", "quantity": 2, "external_tracking_number": "TRK-DUP-1"},
        ],
    )
    await service.start_receiving(order.id)

    with pytest.raises(HTTPException) as exc:
        await service.scan_label(order.id, "TRK-DUP-1")

    assert exc.value.status_code == 409
    assert "matches multiple" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_receive_label_generates_handling_unit_on_confirm(
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
        SKU(
            id="sku-hu-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-001",
            name="HU Item",
        )
    )
    await db.flush()
    db.add(
        Zone(
            id="zone-hu-create",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        Location(
            id="staging-hu-create",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-hu-create",
            barcode="STAGE-HU-CREATE",
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
        order_number="ASN-HU-001",
        lines=[
            {
                "sku_id": "sku-hu-1",
                "quantity": 4,
                "external_carton_mark": "HU-CARTON-001",
            }
        ],
    )

    await service.start_receiving(order.id)
    receipt = await service.receive_label(
        order_id=order.id,
        label_code="HU-CARTON-001",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-hu-create",
    )

    handling_units = (
        (
            await db.execute(
                select(HandlingUnit)
                .where(HandlingUnit.order_id == order.id)
                .order_by(HandlingUnit.unit_code.asc())
            )
        )
        .scalars()
        .all()
    )

    assert len(handling_units) == 1
    assert handling_units[0].unit_code == "RCV-ASN-HU-001-001"
    assert handling_units[0].unit_type == "carton"
    assert handling_units[0].status == "staged"
    assert handling_units[0].external_carton_mark == "HU-CARTON-001"
    assert receipt["handling_unit_code"] == "RCV-ASN-HU-001-001"


@pytest.mark.asyncio
async def test_complete_receiving_marks_handling_unit_putaway_pending(
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
            id="zone-hu-1", tenant_id=tenant_id, warehouse_id=warehouse_id, name="Dock", code="DOCK"
        )
    )
    db.add(
        SKU(
            id="sku-hu-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-HU-002",
            name="HU Item 2",
        )
    )
    db.add(
        Location(
            id="staging-hu-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-hu-1",
            barcode="STAGE-HU-01",
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
        order_number="ASN-HU-002",
        lines=[{"sku_id": "sku-hu-2", "quantity": 6, "external_tracking_number": "HU-TRACK-002"}],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="HU-TRACK-002",
        quantity_received=6,
        quantity_damaged=1,
        staging_location_id="staging-hu-1",
        user_id=user_id,
    )
    await service.complete_receiving(order.id, user_id=user_id)

    handling_unit = await db.scalar(select(HandlingUnit).where(HandlingUnit.order_id == order.id))
    assert handling_unit is not None
    assert handling_unit.status == "putaway_pending"
    assert handling_unit.received_qty == 5
    assert handling_unit.damaged_qty == 1


@pytest.mark.asyncio
async def test_receive_label_updates_receipt_and_inventory(
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
            id="zone-rcv-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OIL-006",
            name="Oil",
        )
    )
    db.add(
        Location(
            id="staging-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-rcv-1",
            barcode="STAGE-01",
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
        order_number="ASN-990",
        lines=[{"sku_id": "sku-rcv-1", "quantity": 10}],
    )
    await service.start_receiving(order.id)

    scan = await service.scan_label(order.id, "RCV-ASN-990-001")
    receipt = await service.receive_label(
        order_id=order.id,
        label_code=scan["label_code"],
        quantity_received=10,
        quantity_damaged=2,
        staging_location_id="staging-1",
        pallet_count=1,
        rent_free_days=14,
        package_count=4,
        measured_weight_kg=18.25,
        measured_length_cm=120,
        measured_width_cm=80,
        measured_height_cm=65,
        receiving_note="received on euro pallet",
        user_id=user_id,
    )

    label = await db.scalar(
        select(ReceivingLabel).where(
            ReceivingLabel.order_id == order.id,
            ReceivingLabel.label_code == "RCV-ASN-990-001",
        )
    )
    line = await db.scalar(select(InboundOrderLine).where(InboundOrderLine.id == scan["line_id"]))
    inventory = await db.scalar(
        select(Inventory).where(
            Inventory.tenant_id == tenant_id,
            Inventory.location_id == "staging-1",
            Inventory.sku_id == "sku-rcv-1",
        )
    )
    transaction = await db.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == TransactionType.RECEIVE.value,
        )
    )
    assert receipt["line_id"] == scan["line_id"]
    assert receipt["label_code"] == "RCV-ASN-990-001"
    assert receipt["label_status"] == "received"
    assert receipt["received"] == 10
    assert receipt["damaged"] == 2
    assert label is not None
    assert label.received_qty == 8
    assert label.status == "received"
    assert label.received_at is not None
    assert line is not None
    assert line.quantity_received == 10
    assert line.quantity_damaged == 2
    assert line.staging_location_id == "staging-1"
    assert line.pallet_count == 1
    assert line.rent_free_days == 14
    assert line.package_count == 4
    assert float(line.measured_weight_kg) == 18.25
    assert float(line.measured_length_cm) == 120
    assert float(line.measured_width_cm) == 80
    assert float(line.measured_height_cm) == 65
    assert line.receiving_note == "received on euro pallet"
    assert receipt["pallet_count"] == 1
    assert receipt["rent_free_days"] == 14
    assert receipt["package_count"] == 4
    assert receipt["measured_weight_kg"] == 18.25
    assert receipt["receiving_note"] == "received on euro pallet"
    assert inventory is not None
    assert inventory.quantity_on_hand == 8
    assert transaction is not None
    assert transaction.notes == "Receiving label RCV-ASN-990-001"


@pytest.mark.asyncio
async def test_mark_labels_printed_records_timestamp_and_count_after_confirm(
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
            id="zone-print-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Dock",
            code="DOCK",
        )
    )
    db.add(
        SKU(
            id="sku-rcv-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="DAN-OIL-006",
            name="Oil",
        )
    )
    db.add(
        Location(
            id="staging-print-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-print-1",
            barcode="STAGE-PRINT-01",
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
        order_number="ASN-PRINT-001",
        lines=[
            {"sku_id": "sku-rcv-1", "quantity": 4, "external_tracking_number": "PRINT-TRACK-001"}
        ],
    )
    await service.start_receiving(order.id)
    await service.receive_label(
        order_id=order.id,
        label_code="PRINT-TRACK-001",
        quantity_received=4,
        quantity_damaged=0,
        staging_location_id="staging-print-1",
    )

    labels = await service.mark_labels_printed(order.id)

    assert len(labels) == 1
    assert labels[0].printed_at is not None
    assert labels[0].extra_data["print_count"] == 1

    labels = await service.mark_labels_printed(order.id, [labels[0].label_code])
    assert labels[0].extra_data["print_count"] == 2
