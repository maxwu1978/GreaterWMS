"""Regression tests: idempotency keys and agent evidence previews (split from tests/test_regressions.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.endpoints.agent as agent_api
from app.api.v1.endpoints.agent import (
    ImportAgentRequest,
    ImportPreviewRequest,
    _tool_preview_inventory_import,
    confirm_import_for_agent,
    get_agent_evidence_detail,
    list_failed_agent_evidence,
    preview_import_for_agent,
    replay_agent_evidence_preview,
)
from app.api.v1.endpoints.picking import ConfirmPickRequest
from app.api.v1.endpoints.picking import confirm_pick as confirm_pick_endpoint
from app.core.security import TokenPayload, UserRole
from app.models.agent_evidence import AgentEvidence
from app.models.client import Client
from app.models.idempotency import IdempotencyRecord
from app.models.inventory import SKU, Inventory, InventoryTransaction, TransactionType
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.models.task import Task, TaskStatus
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.cycle_count_service import CycleCountService
from app.services.idempotency_service import IdempotencyService
from app.services.inventory_rules_service import InventoryRulesService
from app.services.inventory_service import InventoryService
from app.services.picking_service import PickingService
from app.services.shipping_service import ShippingService
from tests.regressions.helpers import setup_pick_fixture


@pytest.mark.asyncio
async def test_confirm_pick_idempotency_key_replays_without_second_inventory_change(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    """Repeating X-Idempotency-Key should return the cached response before mutation code."""
    fixture = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.OPERATOR,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    body = ConfirmPickRequest(task_id=fixture["task_id"], quantity_picked=2)

    first = await confirm_pick_endpoint(
        body=body,
        x_idempotency_key="pick-confirm-key-1",
        current_user=current_user,
        db=db,
    )
    second = await confirm_pick_endpoint(
        body=body,
        x_idempotency_key="pick-confirm-key-1",
        current_user=current_user,
        db=db,
    )

    inv = await db.get(Inventory, fixture["inventory_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.transaction_type == TransactionType.PICK.value,
        )
    )
    records = (await db.execute(select(IdempotencyRecord))).scalars().all()

    assert first == second
    assert first["success"] is True
    assert inv.quantity_on_hand == 8
    assert inv.quantity_allocated == 3
    assert txn_count == 1
    assert len(records) == 1
    assert records[0].status == "completed"


@pytest.mark.asyncio
async def test_pick_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    fixture = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    svc = PickingService(db, tenant_id)

    preview = await svc.preview_pick_confirmation(
        task_id=fixture["task_id"],
        quantity_picked=2,
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    inv = await db.get(Inventory, fixture["inventory_id"])
    task = await db.get(Task, fixture["task_id"])
    line = await db.get(OutboundOrderLine, "line-1")
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.reference_id == "order-1")
    )

    assert preview["ok"] is True
    assert token.startswith("pick-confirm:")
    assert evidence is not None
    assert evidence.status == "previewed"
    assert evidence.confirmation_payload is not None
    assert evidence.confirmation_payload["confirmation_token"] == "[redacted]"
    assert inv is not None
    assert inv.quantity_on_hand == 10
    assert inv.quantity_allocated == 5
    assert task is not None and task.status == TaskStatus.PENDING.value
    assert line is not None and line.quantity_picked == 0
    assert txn_count == 0

    confirmed = await svc.confirm_pick_with_token(
        task_id=fixture["task_id"],
        quantity_picked=2,
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="pick-agent-confirm-1",
    )
    inv = await db.get(Inventory, fixture["inventory_id"])
    task = await db.get(Task, fixture["task_id"])
    line = await db.get(OutboundOrderLine, "line-1")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.reference_id == "order-1")
    )

    assert confirmed["ok"] is True
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert inv is not None
    assert inv.quantity_on_hand == 8
    assert inv.quantity_allocated == 3
    assert task is not None and task.status == TaskStatus.COMPLETED.value
    assert line is not None and line.quantity_picked == 2
    assert txn_count == 1
    assert evidence is not None
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "pick-agent-confirm-1"


@pytest.mark.asyncio
async def test_ship_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Ship Gate 3PL", code="SG3", contact_email="sg@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Ship Client", code="SGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Ship Warehouse", code="SGW"))
    db.add(
        OutboundOrder(
            id="ship-agent-order",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-SHIP-AGENT",
            status=OutboundStatus.PACKED.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="ship-agent-line",
            tenant_id=tenant_id,
            order_id="ship-agent-order",
            sku_id="ship-agent-sku",
            quantity_ordered=3,
            quantity_picked=3,
            quantity_shipped=0,
            pick_location_id="ship-agent-loc",
        )
    )
    await db.flush()
    svc = ShippingService(db, tenant_id)

    preview = await svc.preview_ship_confirmation(
        order_id="ship-agent-order",
        carrier="UPS",
        tracking_number="1ZAGENT",
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    order = await db.get(OutboundOrder, "ship-agent-order")
    line = await db.get(OutboundOrderLine, "ship-agent-line")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.reference_id == "ship-agent-order")
    )

    assert preview["ok"] is True
    assert token.startswith("ship-confirm:")
    assert order is not None and order.status == OutboundStatus.PACKED.value
    assert order.tracking_number is None
    assert line is not None and line.quantity_shipped == 0
    assert txn_count == 0
    assert evidence is not None
    assert evidence.status == "previewed"
    assert evidence.confirmation_payload is not None
    assert evidence.confirmation_payload["confirmation_token"] == "[redacted]"

    confirmed = await svc.confirm_ship_with_token(
        order_id="ship-agent-order",
        carrier="UPS",
        tracking_number="1ZAGENT",
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="ship-agent-confirm-1",
    )
    order = await db.get(OutboundOrder, "ship-agent-order")
    line = await db.get(OutboundOrderLine, "ship-agent-line")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.reference_id == "ship-agent-order")
    )

    assert confirmed["ok"] is True
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert order is not None and order.status == OutboundStatus.SHIPPED.value
    assert order.tracking_number == "1ZAGENT"
    assert line is not None and line.quantity_shipped == 3
    assert txn_count == 1
    assert evidence is not None
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "ship-agent-confirm-1"


@pytest.mark.asyncio
async def test_pack_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Pack Gate 3PL", code="PG3", contact_email="pg@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Pack Client", code="PGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Pack Warehouse", code="PGW"))
    db.add(
        OutboundOrder(
            id="pack-agent-order",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            order_number="OUT-PACK-AGENT",
            status=OutboundStatus.PICKED.value,
        )
    )
    db.add(
        OutboundOrderLine(
            id="pack-agent-line",
            tenant_id=tenant_id,
            order_id="pack-agent-order",
            sku_id="pack-agent-sku",
            quantity_ordered=3,
            quantity_picked=3,
        )
    )
    await db.flush()
    svc = ShippingService(db, tenant_id)

    preview = await svc.preview_pack_verification(
        order_id="pack-agent-order",
        scanned_items=[{"sku_id": "pack-agent-sku", "quantity": 3}],
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    order = await db.get(OutboundOrder, "pack-agent-order")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])

    assert preview["ok"] is True
    assert token.startswith("pack-confirm:")
    assert order is not None and order.status == OutboundStatus.PICKED.value
    assert evidence is not None and evidence.status == "previewed"
    assert evidence.confirmation_payload is not None
    assert evidence.confirmation_payload["confirmation_token"] == "[redacted]"

    confirmed = await svc.confirm_pack_with_token(
        order_id="pack-agent-order",
        scanned_items=[{"sku_id": "pack-agent-sku", "quantity": 3}],
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="pack-agent-confirm-1",
    )
    order = await db.get(OutboundOrder, "pack-agent-order")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])

    assert confirmed["ok"] is True
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert order is not None and order.status == OutboundStatus.PACKED.value
    assert evidence is not None and evidence.status == "executed"
    assert evidence.idempotency_key == "pack-agent-confirm-1"


@pytest.mark.asyncio
async def test_pick_short_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    fixture = await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    svc = PickingService(db, tenant_id)

    preview = await svc.preview_pick_short(
        task_id=fixture["task_id"],
        quantity_available=2,
        reason="Stock short",
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    task = await db.get(Task, fixture["task_id"])
    inv = await db.get(Inventory, fixture["inventory_id"])
    evidence = await db.get(AgentEvidence, preview["evidence_id"])

    assert preview["ok"] is True
    assert token.startswith("pick-short:")
    assert task is not None and task.status == TaskStatus.PENDING.value
    assert inv is not None and inv.quantity_on_hand == 10
    assert evidence is not None and evidence.status == "previewed"

    confirmed = await svc.confirm_pick_short_with_token(
        task_id=fixture["task_id"],
        quantity_available=2,
        reason="Stock short",
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="pick-short-agent-1",
    )
    task = await db.get(Task, fixture["task_id"])
    inv = await db.get(Inventory, fixture["inventory_id"])
    evidence = await db.get(AgentEvidence, preview["evidence_id"])

    assert confirmed["ok"] is True
    assert confirmed["action"] == "picking.short"
    assert task is not None and task.status == TaskStatus.COMPLETED.value
    assert inv is not None and inv.quantity_on_hand == 8
    assert evidence is not None and evidence.status == "executed"
    assert evidence.idempotency_key == "pick-short-agent-1"


@pytest.mark.asyncio
async def test_inventory_adjust_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Adjust Gate 3PL", code="AG3", contact_email="ag@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Adjust Client", code="AGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Adjust Warehouse", code="AGW"))
    db.add(
        Zone(id="adjust-zone", tenant_id=tenant_id, warehouse_id=warehouse_id, name="A", code="A")
    )
    db.add(
        Location(
            id="adjust-loc",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="adjust-zone",
            barcode="ADJ-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
        )
    )
    db.add(
        SKU(
            id="adjust-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="ADJ",
            name="Adjust SKU",
        )
    )
    db.add(
        Inventory(
            id="adjust-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="adjust-loc",
            sku_id="adjust-sku",
            quantity_on_hand=10,
            quantity_allocated=2,
        )
    )
    await db.flush()
    svc = InventoryService(db, tenant_id)

    preview = await svc.preview_adjust_inventory(
        inventory_id="adjust-inv",
        new_quantity=7,
        reason="Cycle count variance",
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    inv = await db.get(Inventory, "adjust-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "adjust-sku")
    )

    assert preview["ok"] is True
    assert token.startswith("inv-adjust:")
    assert inv is not None and inv.quantity_on_hand == 10
    assert txn_count == 0
    assert evidence is not None
    assert evidence.status == "previewed"
    assert evidence.confirmation_payload is not None
    assert evidence.confirmation_payload["confirmation_token"] == "[redacted]"

    confirmed = await svc.confirm_adjust_inventory_with_token(
        inventory_id="adjust-inv",
        new_quantity=7,
        reason="Cycle count variance",
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="inventory-adjust-agent-1",
    )
    inv = await db.get(Inventory, "adjust-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "adjust-sku")
    )

    assert confirmed["ok"] is True
    assert confirmed["evidence_id"] == preview["evidence_id"]
    assert inv is not None and inv.quantity_on_hand == 7
    assert txn_count == 1
    assert evidence is not None
    assert evidence.status == "executed"
    assert evidence.idempotency_key == "inventory-adjust-agent-1"


@pytest.mark.asyncio
async def test_inventory_count_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Count Gate 3PL", code="CG3", contact_email="cg@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Count Client", code="CGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Count Warehouse", code="CGW"))
    db.add(Zone(id="count-zone", tenant_id=tenant_id, warehouse_id=warehouse_id, name="C", code="C"))
    db.add(
        Location(
            id="count-loc",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="count-zone",
            barcode="CNT-01",
            aisle="C",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
        )
    )
    db.add(SKU(id="count-sku", tenant_id=tenant_id, client_id=client_id, sku_code="CNT", name="Count SKU"))
    db.add(
        Inventory(
            id="count-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="count-loc",
            sku_id="count-sku",
            quantity_on_hand=10,
        )
    )
    await db.flush()
    svc = CycleCountService(db, tenant_id)

    preview = await svc.preview_record_count(
        location_id="count-loc",
        counts=[{"sku_id": "count-sku", "counted_quantity": 7}],
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    inv = await db.get(Inventory, "count-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "count-sku")
    )

    assert preview["ok"] is True
    assert token.startswith("inv-count:")
    assert inv is not None and inv.quantity_on_hand == 10
    assert txn_count == 0
    assert evidence is not None and evidence.status == "previewed"

    confirmed = await svc.confirm_record_count_with_token(
        location_id="count-loc",
        counts=[{"sku_id": "count-sku", "counted_quantity": 7}],
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="inventory-count-agent-1",
    )
    inv = await db.get(Inventory, "count-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "count-sku")
    )

    assert confirmed["ok"] is True
    assert inv is not None and inv.quantity_on_hand == 7
    assert txn_count == 1
    assert evidence is not None and evidence.status == "executed"
    assert evidence.idempotency_key == "inventory-count-agent-1"


@pytest.mark.asyncio
async def test_inventory_hold_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Hold Gate 3PL", code="HG3", contact_email="hg@example.com"))
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Hold Client", code="HGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Hold Warehouse", code="HGW"))
    db.add(SKU(id="hold-sku", tenant_id=tenant_id, client_id=client_id, sku_code="HLD", name="Hold SKU"))
    db.add(
        Inventory(
            id="hold-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="hold-loc",
            sku_id="hold-sku",
            quantity_on_hand=10,
            quantity_allocated=2,
            quantity_damaged=1,
        )
    )
    await db.flush()
    svc = InventoryRulesService(db, tenant_id)

    preview = await svc.preview_freeze_inventory(
        inventory_id="hold-inv",
        reason="Quality review",
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    inv = await db.get(Inventory, "hold-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "hold-sku")
    )

    assert preview["ok"] is True
    assert token.startswith("inv-hold:")
    assert inv is not None and inv.quantity_damaged == 1
    assert txn_count == 0
    assert evidence is not None and evidence.status == "previewed"

    confirmed = await svc.confirm_freeze_inventory_with_token(
        inventory_id="hold-inv",
        reason="Quality review",
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="inventory-hold-agent-1",
    )
    inv = await db.get(Inventory, "hold-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "hold-sku")
    )

    assert confirmed["ok"] is True
    assert inv is not None and inv.quantity_damaged == 8
    assert txn_count == 1
    assert evidence is not None and evidence.status == "executed"
    assert evidence.idempotency_key == "inventory-hold-agent-1"


@pytest.mark.asyncio
async def test_inventory_release_preview_persists_evidence_without_mutation_and_token_confirms(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Release Gate 3PL",
            code="RG3",
            contact_email="rg@example.com",
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Release Client", code="RGC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Release Warehouse", code="RGW"))
    db.add(
        SKU(
            id="release-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="REL",
            name="Release SKU",
        )
    )
    db.add(
        Inventory(
            id="release-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="release-loc",
            sku_id="release-sku",
            quantity_on_hand=10,
            quantity_allocated=1,
            quantity_damaged=4,
        )
    )
    await db.flush()
    svc = InventoryRulesService(db, tenant_id)

    preview = await svc.preview_unfreeze_inventory(
        inventory_id="release-inv",
        quantity=3,
        reason="QA cleared",
        user_id=user_id,
    )
    token = preview["confirmation_payload"]["confirmation_token"]
    inv = await db.get(Inventory, "release-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "release-sku")
    )

    assert preview["ok"] is True
    assert token.startswith("inv-release:")
    assert inv is not None and inv.quantity_damaged == 4
    assert txn_count == 0
    assert evidence is not None and evidence.status == "previewed"

    confirmed = await svc.confirm_unfreeze_inventory_with_token(
        inventory_id="release-inv",
        quantity=3,
        reason="QA cleared",
        confirmation_token=token,
        user_id=user_id,
        idempotency_key="inventory-release-agent-1",
    )
    inv = await db.get(Inventory, "release-inv")
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    txn_count = await db.scalar(
        select(func.count())
        .select_from(InventoryTransaction)
        .where(InventoryTransaction.sku_id == "release-sku")
    )

    assert confirmed["ok"] is True
    assert inv is not None and inv.quantity_damaged == 1
    assert txn_count == 1
    assert evidence is not None and evidence.status == "executed"
    assert evidence.idempotency_key == "inventory-release-agent-1"


@pytest.mark.asyncio
async def test_inventory_import_preview_reports_mapping_impact_without_mutation(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Import Preview 3PL",
            code="IP3",
            contact_email="ip@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": ["migration.inventory.preview"],
                }
            },
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Import Client", code="IPC"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Import Warehouse", code="IPW"))
    db.add(
        Zone(
            id="import-zone",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Import Zone",
            code="IPZ",
        )
    )
    db.add(
        Location(
            id="import-loc",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="import-zone",
            barcode="IMP-A1",
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
            id="import-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="IMP-SKU",
            name="Import SKU",
        )
    )
    db.add(
        Inventory(
            id="import-inv",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="import-loc",
            sku_id="import-sku",
            quantity_on_hand=5,
            quantity_allocated=0,
            quantity_damaged=0,
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    csv_text = "sku_code,location_barcode,quantity\nIMP-SKU,IMP-A1,7\nMISSING,IMP-A1,2\n"

    preview = await _tool_preview_inventory_import(
        db,
        current_user,
        {"csv_text": csv_text, "file_name": "inventory.csv"},
    )
    inv = await db.get(Inventory, "import-inv")

    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["summary"]["update"] == 1
    assert preview["summary"]["error"] == 1
    assert preview["summary"]["total_quantity_delta"] == 2
    assert preview["row_results"][0]["operation"] == "update"
    assert preview["row_results"][1]["errors"] == ["sku_not_found"]
    assert inv is not None and inv.quantity_on_hand == 5

    confirmable_csv = "sku_code,location_barcode,quantity\nIMP-SKU,IMP-A1,7\n"
    agent_preview = await preview_import_for_agent(
        "inventory",
        ImportPreviewRequest(csv_text=confirmable_csv, file_name="inventory.csv"),
        current_user=current_user,
        db=db,
    )
    assert agent_preview["confirmation_required_for_write"] is True
    assert agent_preview["planned_request"]["endpoint"] == (
        "POST /api/v1/agent/imports/inventory/preview"
    )

    with pytest.raises(HTTPException) as missing_idempotency:
        await confirm_import_for_agent(
            "inventory",
            ImportAgentRequest(
                csv_text=confirmable_csv,
                file_name="inventory.csv",
                confirmation_token=agent_preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key=None,
            current_user=current_user,
            db=db,
        )
    assert missing_idempotency.value.status_code == 400

    confirmed = await confirm_import_for_agent(
        "inventory",
        ImportAgentRequest(
            csv_text=confirmable_csv,
            file_name="inventory.csv",
            confirmation_token=agent_preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="inventory-import-agent-1",
        current_user=current_user,
        db=db,
    )
    replayed = await confirm_import_for_agent(
        "inventory",
        ImportAgentRequest(
            csv_text=confirmable_csv,
            file_name="inventory.csv",
            confirmation_token=agent_preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="inventory-import-agent-1",
        current_user=current_user,
        db=db,
    )
    inv_after = await db.get(Inventory, "import-inv")
    evidence = await db.get(AgentEvidence, agent_preview["evidence_id"])
    assert confirmed == replayed
    assert confirmed["ok"] is True
    assert confirmed["result"]["imported"] == 1
    assert inv_after is not None and inv_after.quantity_on_hand == 7
    assert evidence is not None and evidence.status == "executed"


@pytest.mark.asyncio
async def test_agent_import_confirmation_rejects_token_and_payload_mismatch(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Import Guard 3PL",
            code="IG3",
            contact_email="ig@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": ["migration.inventory.preview"],
                }
            },
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Import Guard Client", code="IGC"))
    db.add(
        Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Import Guard Warehouse", code="IGW")
    )
    db.add(
        Zone(
            id="import-guard-zone",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Import Guard Zone",
            code="IGZ",
        )
    )
    db.add(
        Location(
            id="import-guard-loc",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="import-guard-zone",
            barcode="IG-A1",
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
            id="import-guard-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="IG-SKU",
            name="Import Guard SKU",
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    csv_text = "sku_code,location_barcode,quantity\nIG-SKU,IG-A1,3\n"
    preview = await preview_import_for_agent(
        "inventory",
        ImportPreviewRequest(csv_text=csv_text, file_name="inventory.csv"),
        current_user=current_user,
        db=db,
    )

    with pytest.raises(HTTPException) as wrong_token:
        await confirm_import_for_agent(
            "inventory",
            ImportAgentRequest(
                csv_text=csv_text,
                file_name="inventory.csv",
                confirmation_token="imp-inventory:not-the-preview-token",
            ),
            x_idempotency_key="inventory-import-wrong-token",
            current_user=current_user,
            db=db,
        )
    assert wrong_token.value.status_code == 409
    assert wrong_token.value.detail["code"] == "confirmation_mismatch"

    changed_csv_text = "sku_code,location_barcode,quantity\nIG-SKU,IG-A1,4\n"
    with pytest.raises(HTTPException) as changed_body:
        await confirm_import_for_agent(
            "inventory",
            ImportAgentRequest(
                csv_text=changed_csv_text,
                file_name="inventory.csv",
                confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key="inventory-import-changed-body",
            current_user=current_user,
            db=db,
        )
    assert changed_body.value.status_code == 409
    assert changed_body.value.detail["code"] == "confirmation_mismatch"

    confirmed = await confirm_import_for_agent(
        "inventory",
        ImportAgentRequest(
            csv_text=csv_text,
            file_name="inventory.csv",
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="inventory-import-same-key",
        current_user=current_user,
        db=db,
    )
    assert confirmed["ok"] is True

    with pytest.raises(HTTPException) as reused_key_different_payload:
        await confirm_import_for_agent(
            "inventory",
            ImportAgentRequest(
                csv_text=changed_csv_text,
                file_name="inventory.csv",
                confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key="inventory-import-same-key",
            current_user=current_user,
            db=db,
        )
    assert reused_key_different_payload.value.status_code == 409
    assert "different mutation request" in reused_key_different_payload.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("import_key", "preview_tool", "preview_tool_name", "import_tool_name"),
    [
        (
            "inbound",
            "receiving.inbound.preview_import",
            "_tool_preview_inbound_import",
            "_tool_import_inbound_with_mapping",
        ),
        (
            "outbound",
            "orders.outbound.preview_import",
            "_tool_preview_outbound_import",
            "_tool_import_outbound_with_mapping",
        ),
        (
            "inventory",
            "migration.inventory.preview",
            "_tool_preview_inventory_import",
            "_tool_import_inventory_with_mapping",
        ),
    ],
)
async def test_agent_import_write_rolls_back_partial_success_on_errors(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    monkeypatch: pytest.MonkeyPatch,
    import_key: str,
    preview_tool: str,
    preview_tool_name: str,
    import_tool_name: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Import Rollback 3PL",
            code=f"IR{import_key[0].upper()}",
            contact_email=f"ir-{import_key}@example.com",
            settings={"agent_console": {"enabled": True, "allowed_tools": [preview_tool]}},
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    async def fake_preview(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
        return {
            "ok": True,
            "missing_required": [],
            "summary": {"error": 0},
            "total_rows": 1,
            "mapping_used": {"demo": "demo"},
        }

    async def fake_import(
        db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
    ) -> dict:
        db.add(
            Client(
                id=f"rollback-client-{import_key}",
                tenant_id=tenant.id,
                name=f"Rollback {import_key}",
                code=f"RB{import_key[0].upper()}",
            )
        )
        await db.flush()
        return {
            "imported": 1,
            "errors": [{"row": 2, "error": "late validation failed"}],
            "total_rows": 1,
            "mapping_used": {"demo": "demo"},
        }

    monkeypatch.setattr(agent_api, preview_tool_name, fake_preview)
    monkeypatch.setattr(agent_api, import_tool_name, fake_import)

    preview = await preview_import_for_agent(
        import_key,
        ImportPreviewRequest(csv_text="demo\nvalue\n", file_name=f"{import_key}.csv"),
        current_user=current_user,
        db=db,
    )
    result = await confirm_import_for_agent(
        import_key,
        ImportAgentRequest(
            csv_text="demo\nvalue\n",
            file_name=f"{import_key}.csv",
            confirmation_token=preview["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key=f"{import_key}-import-rollback",
        current_user=current_user,
        db=db,
    )

    rolled_back_client = await db.get(Client, f"rollback-client-{import_key}")
    assert result["ok"] is False
    assert result["result"]["errors"] == [{"row": 2, "error": "late validation failed"}]
    assert rolled_back_client is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("import_key", "preview_tool", "preview_tool_name", "import_tool_name"),
    [
        (
            "inbound",
            "receiving.inbound.preview_import",
            "_tool_preview_inbound_import",
            "_tool_import_inbound_with_mapping",
        ),
        (
            "outbound",
            "orders.outbound.preview_import",
            "_tool_preview_outbound_import",
            "_tool_import_outbound_with_mapping",
        ),
        (
            "inventory",
            "migration.inventory.preview",
            "_tool_preview_inventory_import",
            "_tool_import_inventory_with_mapping",
        ),
    ],
)
async def test_agent_import_exception_rolls_back_and_clears_idempotency(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    monkeypatch: pytest.MonkeyPatch,
    import_key: str,
    preview_tool: str,
    preview_tool_name: str,
    import_tool_name: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Import Exception 3PL",
            code=f"IE{import_key[0].upper()}",
            contact_email=f"ie-{import_key}@example.com",
            settings={"agent_console": {"enabled": True, "allowed_tools": [preview_tool]}},
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    async def fake_preview(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
        return {
            "ok": True,
            "missing_required": [],
            "summary": {"error": 0},
            "total_rows": 1,
            "mapping_used": {"demo": "demo"},
        }

    async def fake_import(
        db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
    ) -> dict:
        db.add(
            Client(
                id=f"exception-client-{import_key}",
                tenant_id=tenant.id,
                name=f"Exception {import_key}",
                code=f"EX{import_key[0].upper()}",
            )
        )
        await db.flush()
        raise RuntimeError("forced import failure after partial flush")

    monkeypatch.setattr(agent_api, preview_tool_name, fake_preview)
    monkeypatch.setattr(agent_api, import_tool_name, fake_import)

    preview = await preview_import_for_agent(
        import_key,
        ImportPreviewRequest(csv_text="demo\nvalue\n", file_name=f"{import_key}.csv"),
        current_user=current_user,
        db=db,
    )

    with pytest.raises(RuntimeError, match="forced import failure"):
        await confirm_import_for_agent(
            import_key,
            ImportAgentRequest(
                csv_text="demo\nvalue\n",
                file_name=f"{import_key}.csv",
                confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key=f"{import_key}-import-exception",
            current_user=current_user,
            db=db,
        )

    rolled_back_client = await db.get(Client, f"exception-client-{import_key}")
    idempotency_record = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.idempotency_key == f"{import_key}-import-exception",
        )
    )
    evidence = await db.get(AgentEvidence, preview["evidence_id"])
    assert rolled_back_client is None
    assert idempotency_record is None
    assert evidence is not None and evidence.status == "previewed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("import_key", "preview_tool", "preview_tool_name", "import_tool_name"),
    [
        (
            "inbound",
            "receiving.inbound.preview_import",
            "_tool_preview_inbound_import",
            "_tool_import_inbound_with_mapping",
        ),
        (
            "outbound",
            "orders.outbound.preview_import",
            "_tool_preview_outbound_import",
            "_tool_import_outbound_with_mapping",
        ),
        (
            "inventory",
            "migration.inventory.preview",
            "_tool_preview_inventory_import",
            "_tool_import_inventory_with_mapping",
        ),
    ],
)
async def test_agent_import_idempotency_replay_and_payload_mismatch_for_all_families(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    monkeypatch: pytest.MonkeyPatch,
    import_key: str,
    preview_tool: str,
    preview_tool_name: str,
    import_tool_name: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Import Idempotency 3PL",
            code=f"II{import_key[0].upper()}",
            contact_email=f"ii-{import_key}@example.com",
            settings={"agent_console": {"enabled": True, "allowed_tools": [preview_tool]}},
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )
    import_calls: list[str] = []

    async def fake_preview(db: AsyncSession, current_user: TokenPayload, args: dict) -> dict:
        return {
            "ok": True,
            "missing_required": [],
            "summary": {"error": 0},
            "total_rows": 1,
            "mapping_used": {"demo": "demo"},
        }

    async def fake_import(
        db: AsyncSession, tenant: Tenant, current_user: TokenPayload, args: dict
    ) -> dict:
        import_calls.append(args["csv_text"])
        return {
            "imported": 1,
            "errors": [],
            "total_rows": 1,
            "mapping_used": {"demo": "demo"},
            "source_csv": args["csv_text"],
        }

    monkeypatch.setattr(agent_api, preview_tool_name, fake_preview)
    monkeypatch.setattr(agent_api, import_tool_name, fake_import)

    original_csv = "demo\nvalue\n"
    preview = await preview_import_for_agent(
        import_key,
        ImportPreviewRequest(csv_text=original_csv, file_name=f"{import_key}.csv"),
        current_user=current_user,
        db=db,
    )
    request = ImportAgentRequest(
        csv_text=original_csv,
        file_name=f"{import_key}.csv",
        confirmation_token=preview["confirmation_payload"]["confirmation_token"],
    )
    first = await confirm_import_for_agent(
        import_key,
        request,
        x_idempotency_key=f"{import_key}-import-replay",
        current_user=current_user,
        db=db,
    )
    replay = await confirm_import_for_agent(
        import_key,
        request,
        x_idempotency_key=f"{import_key}-import-replay",
        current_user=current_user,
        db=db,
    )

    with pytest.raises(HTTPException) as reused_key_different_payload:
        await confirm_import_for_agent(
            import_key,
            ImportAgentRequest(
                csv_text="demo\nchanged\n",
                file_name=f"{import_key}.csv",
                confirmation_token=preview["confirmation_payload"]["confirmation_token"],
            ),
            x_idempotency_key=f"{import_key}-import-replay",
            current_user=current_user,
            db=db,
        )

    assert first == replay
    assert first["ok"] is True
    assert import_calls == [original_csv]
    assert reused_key_different_payload.value.status_code == 409
    assert "different mutation request" in reused_key_different_payload.value.detail


@pytest.mark.asyncio
async def test_agent_evidence_detail_failed_and_replay_preview_are_read_only(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
):
    db.add(Tenant(id=tenant_id, name="Evidence 3PL", code="EV3", contact_email="ev@example.com"))
    evidence = AgentEvidence(
        id="evidence-read-1",
        tenant_id=tenant_id,
        action="inventory.hold",
        risk="medium",
        required_permission="master_data.manage",
        entity_type="inventory",
        entity_id="inv-1",
        actor_user_id=user_id,
        status="failed",
        payload_hash="abc123",
        confirmation_token_hash="token123",
        planned_endpoint="POST /api/v1/inventory/rules/freeze/preview",
        state_before={"quantity_damaged": 0},
        state_after={"quantity_damaged": 5},
        planned_request={"endpoint": "POST /api/v1/inventory/rules/freeze/preview"},
        confirmation_payload={"confirmation_token": "[redacted]"},
        result={"ok": False},
        failure_reason="confirmation_mismatch",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(evidence)
    await db.flush()
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.TENANT_ADMIN,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    detail = await get_agent_evidence_detail("evidence-read-1", current_user, db)
    failed = await list_failed_agent_evidence(None, 20, current_user, db)
    replay = await replay_agent_evidence_preview("evidence-read-1", current_user, db)

    assert detail["id"] == "evidence-read-1"
    assert detail["failure_reason"] == "confirmation_mismatch"
    assert failed["count"] == 1
    assert replay["ok"] is True
    assert replay["dry_run"] is True
    assert replay["planned_request"]["endpoint"].endswith("/freeze/preview")


@pytest.mark.asyncio
async def test_confirm_pick_idempotency_key_rejects_different_payload(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    user_id: str,
):
    await setup_pick_fixture(db, tenant_id, client_id, warehouse_id)
    current_user = TokenPayload(
        sub=user_id,
        tenant_id=tenant_id,
        role=UserRole.OPERATOR,
        exp=datetime.now(UTC) + timedelta(hours=1),
    )

    await confirm_pick_endpoint(
        body=ConfirmPickRequest(task_id="task-1", quantity_picked=2),
        x_idempotency_key="pick-confirm-key-2",
        current_user=current_user,
        db=db,
    )

    with pytest.raises(HTTPException) as exc_info:
        await confirm_pick_endpoint(
            body=ConfirmPickRequest(task_id="task-1", quantity_picked=3),
            x_idempotency_key="pick-confirm-key-2",
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "different mutation request" in exc_info.value.detail


@pytest.mark.asyncio
async def test_idempotency_key_handler_error_does_not_leave_in_progress(
    db: AsyncSession,
    tenant_id: str,
):
    async def fail_handler():
        raise RuntimeError("simulated handler failure")

    with pytest.raises(RuntimeError):
        await IdempotencyService(db, tenant_id).run(
            key="failure-key-1",
            operation="test.failure",
            request_payload={"body": {"id": "payload-1"}},
            handler=fail_handler,
        )

    records = (
        await db.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.tenant_id == tenant_id,
                IdempotencyRecord.idempotency_key == "failure-key-1",
            )
        )
    ).scalars().all()

    assert records == []


@pytest.mark.asyncio
async def test_idempotency_key_validation_rejects_blank_and_oversized_keys(
    db: AsyncSession,
    tenant_id: str,
):
    async def handler():
        return {"success": True}

    with pytest.raises(HTTPException) as blank_exc:
        await IdempotencyService(db, tenant_id).run(
            key="   ",
            operation="test.validation",
            request_payload={"body": {"id": "blank"}},
            handler=handler,
        )

    with pytest.raises(HTTPException) as long_exc:
        await IdempotencyService(db, tenant_id).run(
            key="x" * 129,
            operation="test.validation",
            request_payload={"body": {"id": "long"}},
            handler=handler,
        )

    assert blank_exc.value.status_code == 400
    assert long_exc.value.status_code == 400


@pytest.mark.asyncio
async def test_idempotency_key_is_scoped_by_tenant(db: AsyncSession):
    async def tenant_a_handler():
        return {"tenant": "a", "success": True}

    async def tenant_b_handler():
        return {"tenant": "b", "success": True}

    first = await IdempotencyService(db, "tenant-idem-a").run(
        key="shared-key-1",
        operation="test.tenant_scope",
        request_payload={"body": {"tenant": "a"}},
        handler=tenant_a_handler,
    )
    second = await IdempotencyService(db, "tenant-idem-b").run(
        key="shared-key-1",
        operation="test.tenant_scope",
        request_payload={"body": {"tenant": "b", "different": True}},
        handler=tenant_b_handler,
    )

    records = (
        await db.execute(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.idempotency_key == "shared-key-1")
            .order_by(IdempotencyRecord.tenant_id)
        )
    ).scalars().all()

    assert first == {"tenant": "a", "success": True}
    assert second == {"tenant": "b", "success": True}
    assert [(record.tenant_id, record.status) for record in records] == [
        ("tenant-idem-a", "completed"),
        ("tenant-idem-b", "completed"),
    ]
