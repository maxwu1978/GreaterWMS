"""Explicit repair helpers for historical putaway task gaps."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.order import HandlingUnit, InboundOrder, InboundOrderLine, InboundStatus
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.services.putaway_execution_service import PutawayExecutionService


@dataclass(slots=True)
class PutawayTaskRepairStats:
    scanned_orders: int = 0
    created_tasks: int = 0
    updated_tasks: int = 0
    skipped_orders: int = 0
    errors: list[str] = field(default_factory=list)


async def repair_missing_putaway_tasks(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    warehouse_id: str | None = None,
    inbound_order_id: str | None = None,
    dry_run: bool = False,
    limit: int = 100,
) -> PutawayTaskRepairStats:
    """Backfill missing putaway tasks outside hot task-list reads."""
    stats = PutawayTaskRepairStats()
    query = select(InboundOrder).where(InboundOrder.status == InboundStatus.PUTAWAY.value)
    if tenant_id:
        query = query.where(InboundOrder.tenant_id == tenant_id)
    if warehouse_id:
        query = query.where(InboundOrder.warehouse_id == warehouse_id)
    if inbound_order_id:
        query = query.where(InboundOrder.id == inbound_order_id)

    result = await db.execute(query.order_by(InboundOrder.created_at).limit(limit))
    orders = result.scalars().all()

    for order in orders:
        stats.scanned_orders += 1
        before = stats.created_tasks + stats.updated_tasks
        try:
            await _repair_order(db, order, stats, dry_run=dry_run)
        except Exception as exc:  # pragma: no cover - defensive support diagnostics
            stats.errors.append(f"{order.order_number or order.id}: {exc}")
        if before == stats.created_tasks + stats.updated_tasks:
            stats.skipped_orders += 1

    if not dry_run:
        await db.flush()

    return stats


async def _repair_order(
    db: AsyncSession,
    order: InboundOrder,
    stats: PutawayTaskRepairStats,
    *,
    dry_run: bool,
) -> None:
    handling_units = (
        await db.execute(
            select(HandlingUnit)
            .where(
                HandlingUnit.tenant_id == order.tenant_id,
                HandlingUnit.order_id == order.id,
            )
            .order_by(HandlingUnit.created_at)
        )
    ).scalars().all()

    if handling_units:
        for handling_unit in handling_units:
            await _repair_handling_unit_task(db, order, handling_unit, stats, dry_run=dry_run)
        return

    lines = (
        await db.execute(
            select(InboundOrderLine)
            .where(
                InboundOrderLine.tenant_id == order.tenant_id,
                InboundOrderLine.order_id == order.id,
            )
            .order_by(InboundOrderLine.created_at)
        )
    ).scalars().all()

    for line in lines:
        await _repair_legacy_line_task(db, order, line, stats, dry_run=dry_run)


async def _repair_handling_unit_task(
    db: AsyncSession,
    order: InboundOrder,
    handling_unit: HandlingUnit,
    stats: PutawayTaskRepairStats,
    *,
    dry_run: bool,
) -> None:
    good_qty = max(0, int(handling_unit.received_qty or 0) - int(handling_unit.damaged_qty or 0))
    if good_qty <= 0 or not handling_unit.staging_location_id:
        return

    existing = await db.scalar(
        select(Task)
        .where(
            Task.tenant_id == order.tenant_id,
            Task.task_type == TaskType.PUTAWAY.value,
            Task.status != TaskStatus.CANCELLED.value,
            Task.handling_unit_id == handling_unit.id,
        )
        .limit(1)
    )
    if existing:
        return

    legacy_candidates = (
        await db.execute(
            select(Task).where(
                Task.tenant_id == order.tenant_id,
                Task.reference_type == "inbound_order",
                Task.reference_id == order.id,
                Task.task_type == TaskType.PUTAWAY.value,
                Task.status != TaskStatus.CANCELLED.value,
                Task.handling_unit_id.is_(None),
                Task.sku_id == handling_unit.sku_id,
                Task.source_location_id == handling_unit.staging_location_id,
            )
        )
    ).scalars().all()
    if len(legacy_candidates) == 1:
        if not dry_run:
            legacy_candidates[0].handling_unit_id = handling_unit.id
        stats.updated_tasks += 1
        return

    inventory_qty = await _available_inventory(
        db,
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        location_id=handling_unit.staging_location_id,
        sku_id=handling_unit.sku_id,
    )
    task_qty = min(good_qty, inventory_qty)
    if task_qty <= 0:
        return

    if not dry_run:
        execution = await PutawayExecutionService(db, order.tenant_id).decide(
            warehouse_id=order.warehouse_id,
            source_location_id=handling_unit.staging_location_id,
            handling_unit_id=handling_unit.id,
        )
        db.add(
            Task(
                tenant_id=order.tenant_id,
                warehouse_id=order.warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                priority=5,
                sku_id=handling_unit.sku_id,
                quantity=task_qty,
                handling_unit_id=handling_unit.id,
                execution_mode=execution.mode,
                source_location_id=handling_unit.staging_location_id,
                reference_type="inbound_order",
                reference_id=order.id,
                assigned_type=AssignedType.UNASSIGNED.value,
            )
        )
    stats.created_tasks += 1


async def _repair_legacy_line_task(
    db: AsyncSession,
    order: InboundOrder,
    line: InboundOrderLine,
    stats: PutawayTaskRepairStats,
    *,
    dry_run: bool,
) -> None:
    good_qty = max(0, int(line.quantity_received or 0) - int(line.quantity_damaged or 0))
    if good_qty <= 0 or not line.staging_location_id:
        return

    existing = await db.scalar(
        select(Task)
        .where(
            Task.tenant_id == order.tenant_id,
            Task.reference_type == "inbound_order",
            Task.reference_id == order.id,
            Task.task_type == TaskType.PUTAWAY.value,
            Task.status != TaskStatus.CANCELLED.value,
            Task.handling_unit_id.is_(None),
            Task.sku_id == line.sku_id,
            Task.source_location_id == line.staging_location_id,
        )
        .limit(1)
    )
    if existing:
        return

    inventory_qty = await _available_inventory(
        db,
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        location_id=line.staging_location_id,
        sku_id=line.sku_id,
    )
    task_qty = min(good_qty, inventory_qty)
    if task_qty <= 0:
        return

    if not dry_run:
        execution = await PutawayExecutionService(db, order.tenant_id).decide(
            warehouse_id=order.warehouse_id,
            source_location_id=line.staging_location_id,
        )
        db.add(
            Task(
                tenant_id=order.tenant_id,
                warehouse_id=order.warehouse_id,
                task_type=TaskType.PUTAWAY.value,
                status=TaskStatus.PENDING.value,
                priority=5,
                sku_id=line.sku_id,
                quantity=task_qty,
                execution_mode=execution.mode,
                source_location_id=line.staging_location_id,
                reference_type="inbound_order",
                reference_id=order.id,
                assigned_type=AssignedType.UNASSIGNED.value,
            )
        )
    stats.created_tasks += 1


async def _available_inventory(
    db: AsyncSession,
    *,
    tenant_id: str,
    warehouse_id: str,
    location_id: str,
    sku_id: str,
) -> int:
    quantity = await db.scalar(
        select(func.coalesce(func.sum(Inventory.quantity_on_hand), 0)).where(
            Inventory.tenant_id == tenant_id,
            Inventory.warehouse_id == warehouse_id,
            Inventory.location_id == location_id,
            Inventory.sku_id == sku_id,
        )
    )
    return int(quantity or 0)
