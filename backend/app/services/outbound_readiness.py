"""Outbound operational readiness projection helpers."""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus

PICK_READINESS_RANKS = {
    "short_stock": 10,
    "ready_to_allocate": 20,
    "ready_to_release": 30,
    "pick_tasks_released": 40,
    "ready_to_pack": 50,
    "ready_to_ship": 60,
    "shipped": 70,
    "no_lines": 80,
    "not_applicable": 90,
}

SHIPPING_READINESS_RANKS = {
    "ready_to_ship": 10,
    "missing_handoff_details": 20,
    "packing": 30,
    "ready_to_pack": 40,
    "shipped": 70,
    "not_applicable": 90,
}


@dataclass
class OutboundReadinessChange:
    order_id: str
    order_number: str
    status: str
    pick_readiness: str
    old_pick_rank: int
    new_pick_rank: int
    old_shipping_rank: int
    new_shipping_rank: int


@dataclass
class OutboundReadinessRefreshStats:
    tenant_id: str
    scanned_orders: int = 0
    updated_orders: int = 0
    unchanged_orders: int = 0
    dry_run: bool = False
    changes: list[OutboundReadinessChange] = field(default_factory=list)


def pick_readiness_from_summary(status: str, total_items: int, shortage_units: int) -> str:
    if status == OutboundStatus.PENDING.value:
        if total_items <= 0:
            return "no_lines"
        if shortage_units > 0:
            return "short_stock"
        return "ready_to_allocate"
    if status == OutboundStatus.ALLOCATED.value:
        return "ready_to_release"
    if status == OutboundStatus.PICKING.value:
        return "pick_tasks_released"
    if status == OutboundStatus.PICKED.value:
        return "ready_to_pack"
    if status == OutboundStatus.PACKED.value:
        return "ready_to_ship"
    if status == OutboundStatus.SHIPPED.value:
        return "shipped"
    return "not_applicable"


def pick_readiness_rank(readiness: str) -> int:
    return PICK_READINESS_RANKS.get(readiness, PICK_READINESS_RANKS["not_applicable"])


def shipping_readiness_rank_from_values(
    status: str,
    carrier: str | None = None,
    tracking_number: str | None = None,
) -> int:
    if status == OutboundStatus.PACKED.value:
        if (carrier or "").strip() and (tracking_number or "").strip():
            return SHIPPING_READINESS_RANKS["ready_to_ship"]
        return SHIPPING_READINESS_RANKS["missing_handoff_details"]
    if status == OutboundStatus.PACKING.value:
        return SHIPPING_READINESS_RANKS["packing"]
    if status == OutboundStatus.PICKED.value:
        return SHIPPING_READINESS_RANKS["ready_to_pack"]
    if status == OutboundStatus.SHIPPED.value:
        return SHIPPING_READINESS_RANKS["shipped"]
    return SHIPPING_READINESS_RANKS["not_applicable"]


def apply_outbound_readiness_projection(
    order: OutboundOrder,
    *,
    pick_readiness: str | None = None,
    total_items: int = 1,
    shortage_units: int = 0,
) -> tuple[int, int]:
    resolved_pick_readiness = pick_readiness or pick_readiness_from_summary(
        order.status,
        total_items,
        shortage_units,
    )
    pick_rank = pick_readiness_rank(resolved_pick_readiness)
    shipping_rank = shipping_readiness_rank_from_values(
        order.status,
        order.carrier,
        order.tracking_number,
    )
    order.pick_readiness_rank = pick_rank
    order.shipping_readiness_rank = shipping_rank
    return pick_rank, shipping_rank


async def refresh_outbound_readiness_projection(
    db: AsyncSession,
    tenant_id: str,
    order: OutboundOrder,
) -> tuple[str, int, int]:
    lines_result = await db.execute(
        select(OutboundOrderLine).where(
            OutboundOrderLine.tenant_id == tenant_id,
            OutboundOrderLine.order_id == order.id,
        )
    )
    lines = lines_result.scalars().all()
    total_items = sum(line.quantity_ordered or 0 for line in lines)

    remaining_by_sku: dict[str, int] = defaultdict(int)
    for line in lines:
        remaining_by_sku[line.sku_id] += max(
            0,
            (line.quantity_ordered or 0) - (line.quantity_allocated or 0),
        )

    available_by_sku: dict[str, int] = defaultdict(int)
    if remaining_by_sku:
        inventory_result = await db.execute(
            select(Inventory).where(
                Inventory.tenant_id == tenant_id,
                Inventory.warehouse_id == order.warehouse_id,
                Inventory.sku_id.in_(list(remaining_by_sku)),
            )
        )
        for item in inventory_result.scalars().all():
            available_by_sku[item.sku_id] += max(
                0,
                (item.quantity_on_hand or 0)
                - (item.quantity_allocated or 0)
                - (item.quantity_damaged or 0),
            )

    shortage_units = sum(
        max(0, needed - available_by_sku.get(sku_id, 0))
        for sku_id, needed in remaining_by_sku.items()
    )
    readiness = pick_readiness_from_summary(order.status, total_items, shortage_units)
    apply_outbound_readiness_projection(order, pick_readiness=readiness)
    return readiness, total_items, shortage_units


async def refresh_outbound_readiness_projections(
    db: AsyncSession,
    tenant_id: str,
    *,
    warehouse_id: str | None = None,
    order_id: str | None = None,
    statuses: list[str] | None = None,
    dry_run: bool = False,
    limit: int = 500,
) -> OutboundReadinessRefreshStats:
    active_statuses = statuses or [
        OutboundStatus.PENDING.value,
        OutboundStatus.ALLOCATED.value,
        OutboundStatus.PICKING.value,
        OutboundStatus.PICKED.value,
        OutboundStatus.PACKING.value,
        OutboundStatus.PACKED.value,
        OutboundStatus.SHIPPED.value,
    ]
    query = select(OutboundOrder).where(OutboundOrder.tenant_id == tenant_id)
    if warehouse_id:
        query = query.where(OutboundOrder.warehouse_id == warehouse_id)
    if order_id:
        query = query.where(OutboundOrder.id == order_id)
    if active_statuses:
        query = query.where(OutboundOrder.status.in_(active_statuses))

    result = await db.execute(query.order_by(OutboundOrder.created_at.desc()).limit(limit))
    orders = result.scalars().all()
    stats = OutboundReadinessRefreshStats(
        tenant_id=tenant_id,
        scanned_orders=len(orders),
        dry_run=dry_run,
    )

    for order in orders:
        old_pick_rank = order.pick_readiness_rank
        old_shipping_rank = order.shipping_readiness_rank
        readiness, _total_items, _shortage_units = await refresh_outbound_readiness_projection(
            db,
            tenant_id,
            order,
        )
        changed = (
            order.pick_readiness_rank != old_pick_rank
            or order.shipping_readiness_rank != old_shipping_rank
        )
        if changed:
            stats.updated_orders += 1
            stats.changes.append(
                OutboundReadinessChange(
                    order_id=order.id,
                    order_number=order.order_number,
                    status=order.status,
                    pick_readiness=readiness,
                    old_pick_rank=old_pick_rank,
                    new_pick_rank=order.pick_readiness_rank,
                    old_shipping_rank=old_shipping_rank,
                    new_shipping_rank=order.shipping_readiness_rank,
                )
            )
            if dry_run:
                order.pick_readiness_rank = old_pick_rank
                order.shipping_readiness_rank = old_shipping_rank
        else:
            stats.unchanged_orders += 1

    if not dry_run:
        await db.flush()
    return stats


async def refresh_pending_outbound_readiness_for_inventory_change(
    db: AsyncSession,
    tenant_id: str,
    *,
    warehouse_id: str,
    sku_ids: list[str] | set[str] | tuple[str, ...],
    limit: int = 500,
) -> OutboundReadinessRefreshStats:
    """Refresh pending outbound readiness for stock changes in one warehouse.

    Inventory imports, manual adjustments, and cycle counts can change whether a
    pending outbound order is short-stocked without touching the outbound order
    itself. Keep this scoped to affected SKUs so hot inventory paths do not
    trigger a tenant-wide readiness rebuild.
    """

    normalized_sku_ids = sorted({sku_id for sku_id in sku_ids if sku_id})
    stats = OutboundReadinessRefreshStats(tenant_id=tenant_id)
    if not warehouse_id or not normalized_sku_ids:
        return stats

    result = await db.execute(
        select(OutboundOrder)
        .join(
            OutboundOrderLine,
            OutboundOrderLine.order_id == OutboundOrder.id,
        )
        .where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.warehouse_id == warehouse_id,
            OutboundOrder.status == OutboundStatus.PENDING.value,
            OutboundOrderLine.tenant_id == tenant_id,
            OutboundOrderLine.sku_id.in_(normalized_sku_ids),
        )
        .order_by(OutboundOrder.created_at.desc())
        .limit(limit)
    )
    orders = result.unique().scalars().all()
    stats.scanned_orders = len(orders)

    for order in orders:
        old_pick_rank = order.pick_readiness_rank
        old_shipping_rank = order.shipping_readiness_rank
        readiness, _total_items, _shortage_units = await refresh_outbound_readiness_projection(
            db,
            tenant_id,
            order,
        )
        changed = (
            order.pick_readiness_rank != old_pick_rank
            or order.shipping_readiness_rank != old_shipping_rank
        )
        if changed:
            stats.updated_orders += 1
            stats.changes.append(
                OutboundReadinessChange(
                    order_id=order.id,
                    order_number=order.order_number,
                    status=order.status,
                    pick_readiness=readiness,
                    old_pick_rank=old_pick_rank,
                    new_pick_rank=order.pick_readiness_rank,
                    old_shipping_rank=old_shipping_rank,
                    new_shipping_rank=order.shipping_readiness_rank,
                )
            )
        else:
            stats.unchanged_orders += 1

    await db.flush()
    return stats
