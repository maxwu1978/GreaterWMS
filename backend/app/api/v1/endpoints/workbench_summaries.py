"""Lightweight workbench summary endpoints for high-traffic operational pages."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.security import TokenPayload, UserRole
from app.models.inventory import Inventory
from app.models.order import (
    InboundOrder,
    InboundPackage,
    InboundPackageStatus,
    OutboundOrder,
    OutboundOrderLine,
    ReceivingLabel,
)
from app.models.task import Task, TaskStatus, TaskType

router = APIRouter()


class ReceivingWorkbenchSummary(BaseModel):
    total_orders: int
    active_orders: int
    archived_orders: int
    voided_orders: int
    completed_orders: int
    by_status: dict[str, int]
    packages_open: int
    packages_putaway_pending: int
    packages_stored: int
    internal_labels_print_pending: int


class PutawayWorkbenchSummary(BaseModel):
    total_tasks: int
    pending_tasks: int
    assigned_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_units: int
    by_status: dict[str, int]
    by_assigned_type: dict[str, int]


class PickingWorkbenchSummary(BaseModel):
    total_orders: int
    by_status: dict[str, int]
    total_ordered_units: int
    total_allocated_units: int
    total_picked_units: int
    pending_pick_tasks: int
    active_pick_tasks: int


class InventoryWorkbenchSummary(BaseModel):
    inventory_rows: int
    client_count: int
    sku_count: int
    location_count: int
    on_hand_units: int
    allocated_units: int
    damaged_units: int
    available_units: int


def _int(value: Any) -> int:
    return int(value or 0)


def _tenant_client_filter(model: Any, current_user: TokenPayload, client_id: str | None = None):
    filters = [model.tenant_id == current_user.tenant_id]
    if current_user.role == UserRole.CLIENT_VIEWER and current_user.client_id:
        filters.append(model.client_id == current_user.client_id)
    elif client_id:
        filters.append(model.client_id == client_id)
    return filters


@router.get("/receiving", response_model=ReceivingWorkbenchSummary)
async def receiving_summary(
    warehouse_id: str | None = Query(None),
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    order_filters = _tenant_client_filter(InboundOrder, current_user, client_id)
    if warehouse_id:
        order_filters.append(InboundOrder.warehouse_id == warehouse_id)

    order_status_result = await db.execute(
        select(InboundOrder.status, func.count())
        .where(*order_filters)
        .group_by(InboundOrder.status)
    )
    by_status = {str(status): _int(count) for status, count in order_status_result.all()}
    total_orders = sum(by_status.values())
    completed_orders = by_status.get("completed", 0)

    archived_flag = func.coalesce(InboundOrder.extra_data["archived"].as_boolean(), False)
    voided_flag = func.coalesce(InboundOrder.extra_data["voided"].as_boolean(), False)
    flag_result = await db.execute(
        select(
            func.coalesce(func.sum(case((archived_flag, 1), else_=0)), 0),
            func.coalesce(func.sum(case((voided_flag, 1), else_=0)), 0),
        ).where(*order_filters)
    )
    archived_count, voided_count = flag_result.one()
    archived_orders = _int(archived_count)
    voided_orders = _int(voided_count)

    order_ids_subquery = select(InboundOrder.id).where(*order_filters)

    package_filters = [InboundPackage.tenant_id == current_user.tenant_id]
    if warehouse_id or client_id or current_user.role == UserRole.CLIENT_VIEWER:
        package_filters.append(InboundPackage.order_id.in_(order_ids_subquery))
    package_status_result = await db.execute(
        select(InboundPackage.status, func.count()).where(*package_filters).group_by(InboundPackage.status)
    )
    package_counts = {str(status): _int(count) for status, count in package_status_result.all()}

    label_filters = [ReceivingLabel.tenant_id == current_user.tenant_id]
    if warehouse_id or client_id or current_user.role == UserRole.CLIENT_VIEWER:
        label_filters.append(ReceivingLabel.order_id.in_(order_ids_subquery))
    internal_labels_print_pending = _int(
        await db.scalar(
            select(func.count()).where(
                *label_filters,
                ReceivingLabel.status == "received",
                func.coalesce(ReceivingLabel.extra_data["print_count"].as_integer(), 0) <= 0,
            )
        )
    )

    packages_open = sum(
        package_counts.get(status, 0)
        for status in (
            InboundPackageStatus.EXPECTED.value,
            InboundPackageStatus.RECEIVING.value,
            InboundPackageStatus.RECEIVED.value,
            InboundPackageStatus.STAGED.value,
        )
    )
    return ReceivingWorkbenchSummary(
        total_orders=total_orders,
        active_orders=max(0, total_orders - archived_orders - voided_orders - completed_orders),
        archived_orders=archived_orders,
        voided_orders=voided_orders,
        completed_orders=completed_orders,
        by_status=by_status,
        packages_open=packages_open,
        packages_putaway_pending=package_counts.get(InboundPackageStatus.PUTAWAY_PENDING.value, 0),
        packages_stored=package_counts.get(InboundPackageStatus.STORED.value, 0),
        internal_labels_print_pending=internal_labels_print_pending,
    )


@router.get("/putaway", response_model=PutawayWorkbenchSummary)
async def putaway_summary(
    warehouse_id: str | None = Query(None),
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    filters = [
        Task.tenant_id == current_user.tenant_id,
        Task.task_type == TaskType.PUTAWAY.value,
    ]
    if warehouse_id:
        filters.append(Task.warehouse_id == warehouse_id)
    if client_id or current_user.role == UserRole.CLIENT_VIEWER:
        order_filters = _tenant_client_filter(InboundOrder, current_user, client_id)
        if warehouse_id:
            order_filters.append(InboundOrder.warehouse_id == warehouse_id)
        filters.extend(
            [
                Task.reference_type == "inbound_order",
                Task.reference_id.in_(select(InboundOrder.id).where(*order_filters)),
            ]
        )

    status_result = await db.execute(
        select(Task.status, func.count()).where(*filters).group_by(Task.status)
    )
    by_status = {str(status): _int(count) for status, count in status_result.all()}
    assigned_result = await db.execute(
        select(Task.assigned_type, func.count()).where(*filters).group_by(Task.assigned_type)
    )
    by_assigned_type = {
        str(assigned_type): _int(count) for assigned_type, count in assigned_result.all()
    }
    pending_units = await db.scalar(
        select(func.coalesce(func.sum(Task.quantity), 0)).where(
            *filters, Task.status == TaskStatus.PENDING.value
        )
    )
    return PutawayWorkbenchSummary(
        total_tasks=sum(by_status.values()),
        pending_tasks=by_status.get(TaskStatus.PENDING.value, 0),
        assigned_tasks=by_status.get(TaskStatus.ASSIGNED.value, 0),
        in_progress_tasks=by_status.get(TaskStatus.IN_PROGRESS.value, 0),
        completed_tasks=by_status.get(TaskStatus.COMPLETED.value, 0),
        failed_tasks=by_status.get(TaskStatus.FAILED.value, 0),
        pending_units=_int(pending_units),
        by_status=by_status,
        by_assigned_type=by_assigned_type,
    )


@router.get("/picking", response_model=PickingWorkbenchSummary)
async def picking_summary(
    warehouse_id: str | None = Query(None),
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    order_filters = _tenant_client_filter(OutboundOrder, current_user, client_id)
    if warehouse_id:
        order_filters.append(OutboundOrder.warehouse_id == warehouse_id)

    status_result = await db.execute(
        select(OutboundOrder.status, func.count()).where(*order_filters).group_by(OutboundOrder.status)
    )
    by_status = {str(status): _int(count) for status, count in status_result.all()}
    order_ids_subquery = select(OutboundOrder.id).where(*order_filters)
    line_totals = await db.execute(
        select(
            func.coalesce(func.sum(OutboundOrderLine.quantity_ordered), 0),
            func.coalesce(func.sum(OutboundOrderLine.quantity_allocated), 0),
            func.coalesce(func.sum(OutboundOrderLine.quantity_picked), 0),
        ).where(
            OutboundOrderLine.tenant_id == current_user.tenant_id,
            OutboundOrderLine.order_id.in_(order_ids_subquery),
        )
    )
    total_ordered, total_allocated, total_picked = line_totals.one()

    task_filters = [
        Task.tenant_id == current_user.tenant_id,
        Task.task_type == TaskType.PICK.value,
    ]
    if warehouse_id:
        task_filters.append(Task.warehouse_id == warehouse_id)
    if client_id or current_user.role == UserRole.CLIENT_VIEWER:
        task_filters.extend(
            [
                Task.reference_type == "outbound_order",
                Task.reference_id.in_(order_ids_subquery),
            ]
        )
    task_status_result = await db.execute(
        select(Task.status, func.count()).where(*task_filters).group_by(Task.status)
    )
    pick_task_counts = {str(status): _int(count) for status, count in task_status_result.all()}
    active_pick_tasks = sum(
        pick_task_counts.get(status, 0)
        for status in (
            TaskStatus.PENDING.value,
            TaskStatus.ASSIGNED.value,
            TaskStatus.IN_PROGRESS.value,
        )
    )
    return PickingWorkbenchSummary(
        total_orders=sum(by_status.values()),
        by_status=by_status,
        total_ordered_units=_int(total_ordered),
        total_allocated_units=_int(total_allocated),
        total_picked_units=_int(total_picked),
        pending_pick_tasks=pick_task_counts.get(TaskStatus.PENDING.value, 0),
        active_pick_tasks=active_pick_tasks,
    )


@router.get("/inventory", response_model=InventoryWorkbenchSummary)
async def inventory_summary(
    warehouse_id: str | None = Query(None),
    client_id: str | None = Query(None),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    filters = _tenant_client_filter(Inventory, current_user, client_id)
    filters.append(Inventory.quantity_on_hand > 0)
    if warehouse_id:
        filters.append(Inventory.warehouse_id == warehouse_id)

    result = await db.execute(
        select(
            func.count(Inventory.id),
            func.count(distinct(Inventory.client_id)),
            func.count(distinct(Inventory.sku_id)),
            func.count(distinct(Inventory.location_id)),
            func.coalesce(func.sum(Inventory.quantity_on_hand), 0),
            func.coalesce(func.sum(Inventory.quantity_allocated), 0),
            func.coalesce(func.sum(Inventory.quantity_damaged), 0),
            func.coalesce(
                func.sum(
                    Inventory.quantity_on_hand
                    - Inventory.quantity_allocated
                    - Inventory.quantity_damaged
                ),
                0,
            ),
        ).where(*filters)
    )
    (
        inventory_rows,
        client_count,
        sku_count,
        location_count,
        on_hand_units,
        allocated_units,
        damaged_units,
        available_units,
    ) = result.one()
    return InventoryWorkbenchSummary(
        inventory_rows=_int(inventory_rows),
        client_count=_int(client_count),
        sku_count=_int(sku_count),
        location_count=_int(location_count),
        on_hand_units=_int(on_hand_units),
        allocated_units=_int(allocated_units),
        damaged_units=_int(damaged_units),
        available_units=_int(available_units),
    )
