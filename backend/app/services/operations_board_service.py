"""Build the read-only operations board from existing WMS work records."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.order import (
    InboundOrder,
    InboundOrderLine,
    InboundStatus,
    OutboundOrder,
    OutboundOrderLine,
    OutboundStatus,
)
from app.models.task import Task, TaskStatus, TaskType
from app.models.warehouse import Location

ACTIVE_INBOUND_STATUSES = {
    InboundStatus.EXPECTED.value,
    InboundStatus.ARRIVED.value,
    InboundStatus.RECEIVING.value,
}
ACTIVE_OUTBOUND_STATUSES = {
    OutboundStatus.PENDING.value,
    OutboundStatus.ALLOCATED.value,
    OutboundStatus.PICKING.value,
    OutboundStatus.PICKED.value,
    OutboundStatus.PACKING.value,
    OutboundStatus.PACKED.value,
}
ACTIVE_TASK_STATUSES = {
    TaskStatus.PENDING.value,
    TaskStatus.ASSIGNED.value,
    TaskStatus.IN_PROGRESS.value,
    TaskStatus.FAILED.value,
}
BOARD_TASK_TYPES = {
    TaskType.PUTAWAY.value,
    TaskType.UNLOAD.value,
    TaskType.LOAD.value,
    TaskType.MOVE.value,
    TaskType.REPLENISH.value,
    TaskType.CYCLE_COUNT.value,
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_past(value: datetime | None, now: datetime) -> bool:
    """Treat date-only expected timestamps as due at the end of that day."""
    value = _aware(value)
    if value is None:
        return False
    if value.time() == time.min:
        return value.date() < now.date()
    return value < now


def _lane(
    *,
    due_at: datetime | None,
    now: datetime,
    active: bool = False,
    blocked: bool = False,
) -> str:
    if blocked:
        return "blocked"
    if active:
        return "now"
    if _is_past(due_at, now):
        return "delayed"
    if due_at is None:
        return "now"
    return "next"


def _order_priority(priority: int | None) -> int:
    # Orders use 1 as the highest priority; keep the board sort direction stable.
    return int(priority or 5)


def _task_route(task_type: str) -> tuple[str, str, str]:
    if task_type == TaskType.PUTAWAY.value:
        return "putaway", "/putaway", "open_putaway"
    if task_type == TaskType.UNLOAD.value:
        return "unload", "/receiving", "open_receiving"
    if task_type == TaskType.LOAD.value:
        return "load", "/shipping", "open_shipping"
    if task_type == TaskType.CYCLE_COUNT.value:
        return "cycle_count", "/inventory", "open_inventory"
    if task_type in {TaskType.MOVE.value, TaskType.REPLENISH.value}:
        return task_type, "/inventory", "open_inventory"
    return task_type, "/putaway", "open_putaway"


class OperationsBoardService:
    """Compose a small, tenant-scoped work queue without creating new statuses."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def build(
        self,
        *,
        warehouse_id: str | None = None,
        client_id: str | None = None,
        limit: int = 100,
        include_tasks: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        inbound_orders = await self._inbound_orders(warehouse_id, client_id, limit)
        outbound_orders = await self._outbound_orders(warehouse_id, client_id, limit)

        inbound_ids = {order.id for order in inbound_orders}
        outbound_ids = {order.id for order in outbound_orders}
        inbound_quantities = await self._line_quantities(InboundOrderLine, inbound_ids)
        outbound_quantities = await self._line_quantities(OutboundOrderLine, outbound_ids)

        items: list[dict[str, Any]] = []
        items.extend(self._inbound_items(inbound_orders, inbound_quantities, now))
        items.extend(self._outbound_items(outbound_orders, outbound_quantities, now))

        if include_tasks and not client_id:
            tasks = await self._tasks(warehouse_id, limit)
            task_location_labels = await self._task_locations(tasks)
            task_inbound_refs = {
                task.reference_id
                for task in tasks
                if task.reference_type == "inbound_order" and task.reference_id
            }
            task_outbound_refs = {
                task.reference_id
                for task in tasks
                if task.reference_type == "outbound_order" and task.reference_id
            }
            task_inbound_orders = await self._reference_orders(InboundOrder, task_inbound_refs)
            task_outbound_orders = await self._reference_orders(OutboundOrder, task_outbound_refs)
            items.extend(
                self._task_items(
                    tasks,
                    {
                        **{
                            order.id: (order.order_number, order.client_id)
                            for order in inbound_orders
                        },
                        **task_inbound_orders,
                    },
                    {
                        **{
                            order.id: (order.order_number, order.client_id)
                            for order in outbound_orders
                        },
                        **task_outbound_orders,
                    },
                    task_location_labels,
                    now,
                )
            )

        client_names = await self._client_names(
            {item["client_id"] for item in items if item.get("client_id")}
        )
        for item in items:
            item["client_name"] = client_names.get(item.get("client_id"))

        items.sort(key=lambda item: self._sort_key(item, now))
        lanes = Counter(item["lane"] for item in items)
        operations = Counter(item["operation"] for item in items)
        visible_items = items[:limit]
        return {
            "generated_at": now.isoformat(),
            "warehouse_id": warehouse_id,
            "items": visible_items,
            "counts": {
                "total": len(items),
                "now": lanes.get("now", 0),
                "next": lanes.get("next", 0),
                "delayed": lanes.get("delayed", 0),
                "blocked": lanes.get("blocked", 0),
                "by_operation": dict(operations),
            },
        }

    async def _inbound_orders(
        self,
        warehouse_id: str | None,
        client_id: str | None,
        limit: int,
    ) -> list[InboundOrder]:
        filters = [
            InboundOrder.tenant_id == self.tenant_id,
            InboundOrder.status.in_(ACTIVE_INBOUND_STATUSES),
        ]
        if warehouse_id:
            filters.append(InboundOrder.warehouse_id == warehouse_id)
        if client_id:
            filters.append(InboundOrder.client_id == client_id)
        result = await self.db.execute(
            select(InboundOrder)
            .where(*filters)
            .order_by(InboundOrder.expected_date.asc().nulls_last(), InboundOrder.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _outbound_orders(
        self,
        warehouse_id: str | None,
        client_id: str | None,
        limit: int,
    ) -> list[OutboundOrder]:
        filters = [
            OutboundOrder.tenant_id == self.tenant_id,
            OutboundOrder.status.in_(ACTIVE_OUTBOUND_STATUSES),
        ]
        if warehouse_id:
            filters.append(OutboundOrder.warehouse_id == warehouse_id)
        if client_id:
            filters.append(OutboundOrder.client_id == client_id)
        result = await self.db.execute(
            select(OutboundOrder)
            .where(*filters)
            .order_by(
                OutboundOrder.required_ship_date.asc().nulls_last(),
                OutboundOrder.priority.asc(),
                OutboundOrder.created_at.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _line_quantities(self, model: Any, order_ids: set[str]) -> dict[str, tuple[int, int]]:
        if not order_ids:
            return {}
        if model is InboundOrderLine:
            expected = model.quantity_expected
            progress = model.quantity_received
        else:
            expected = model.quantity_ordered
            progress = model.quantity_picked
        result = await self.db.execute(
            select(
                model.order_id,
                func.coalesce(func.sum(expected), 0),
                func.coalesce(func.sum(progress), 0),
            )
            .where(model.tenant_id == self.tenant_id, model.order_id.in_(order_ids))
            .group_by(model.order_id)
        )
        return {
            order_id: (int(expected_qty or 0), int(progress_qty or 0))
            for order_id, expected_qty, progress_qty in result.all()
        }

    async def _tasks(self, warehouse_id: str | None, limit: int) -> list[Task]:
        filters = [
            Task.tenant_id == self.tenant_id,
            Task.status.in_(ACTIVE_TASK_STATUSES),
            Task.task_type.in_(BOARD_TASK_TYPES),
        ]
        if warehouse_id:
            filters.append(Task.warehouse_id == warehouse_id)
        result = await self.db.execute(
            select(Task)
            .where(*filters)
            .order_by(Task.status.asc(), Task.priority.asc(), Task.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _task_locations(self, tasks: list[Task]) -> dict[str, str]:
        location_ids = {
            location_id
            for task in tasks
            for location_id in (task.source_location_id, task.destination_location_id)
            if location_id
        }
        if not location_ids:
            return {}
        result = await self.db.execute(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.id.in_(location_ids),
            )
        )
        return {location.id: location.barcode for location in result.scalars().all()}

    async def _reference_orders(
        self,
        model: Any,
        order_ids: set[str],
    ) -> dict[str, tuple[str, str]]:
        if not order_ids:
            return {}
        result = await self.db.execute(
            select(model.id, model.order_number, model.client_id).where(
                model.tenant_id == self.tenant_id,
                model.id.in_(order_ids),
            )
        )
        return {
            order_id: (order_number, client_id)
            for order_id, order_number, client_id in result.all()
        }

    async def _client_names(self, client_ids: set[str]) -> dict[str, str]:
        if not client_ids:
            return {}
        result = await self.db.execute(
            select(Client.id, Client.name).where(
                Client.tenant_id == self.tenant_id,
                Client.id.in_(client_ids),
            )
        )
        return {client_id: name for client_id, name in result.all()}

    def _inbound_items(
        self,
        orders: list[InboundOrder],
        quantities: dict[str, tuple[int, int]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        items = []
        for order in orders:
            expected, progress = quantities.get(order.id, (0, 0))
            is_active = order.status in {InboundStatus.ARRIVED.value, InboundStatus.RECEIVING.value}
            operation = "receiving" if order.status != InboundStatus.ARRIVED.value else "unload"
            action_key = (
                "continue_receiving"
                if order.status == InboundStatus.RECEIVING.value
                else "open_receiving"
            )
            items.append(
                {
                    "id": f"inbound:{order.id}",
                    "category": "inbound",
                    "operation": operation,
                    "lane": _lane(due_at=order.expected_date, now=now, active=is_active),
                    "source_status": order.status,
                    "reference_type": "inbound_order",
                    "reference_id": order.id,
                    "reference_number": order.order_number,
                    "client_id": order.client_id,
                    "client_name": None,
                    "priority": 5,
                    "due_at": _iso(order.expected_date),
                    "created_at": _iso(order.created_at),
                    "quantity": expected,
                    "quantity_progress": progress,
                    "location_label": "Dock / staging",
                    "assigned_type": None,
                    "assigned_to": None,
                    "action_key": action_key,
                    "action_route": "/receiving",
                    "blocker_code": None,
                }
            )
        return items

    def _outbound_items(
        self,
        orders: list[OutboundOrder],
        quantities: dict[str, tuple[int, int]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        items = []
        for order in orders:
            expected, progress = quantities.get(order.id, (0, 0))
            if order.status in {
                OutboundStatus.PICKED.value,
                OutboundStatus.PACKING.value,
                OutboundStatus.PACKED.value,
            }:
                operation = "shipping"
                action_key = "open_shipping"
                action_route = "/shipping"
            else:
                operation = "picking"
                action_key = "open_picking"
                action_route = "/picking"
            items.append(
                {
                    "id": f"outbound:{order.id}",
                    "category": "outbound",
                    "operation": operation,
                    "lane": _lane(
                        due_at=order.required_ship_date,
                        now=now,
                        active=order.status
                        in {
                            OutboundStatus.PICKING.value,
                            OutboundStatus.PICKED.value,
                            OutboundStatus.PACKING.value,
                            OutboundStatus.PACKED.value,
                        },
                    ),
                    "source_status": order.status,
                    "reference_type": "outbound_order",
                    "reference_id": order.id,
                    "reference_number": order.order_number,
                    "client_id": order.client_id,
                    "client_name": None,
                    "priority": _order_priority(order.priority),
                    "due_at": _iso(order.required_ship_date),
                    "created_at": _iso(order.created_at),
                    "quantity": expected,
                    "quantity_progress": progress,
                    "location_label": "Storage / shipping",
                    "assigned_type": None,
                    "assigned_to": None,
                    "action_key": action_key,
                    "action_route": action_route,
                    "blocker_code": None,
                }
            )
        return items

    def _task_items(
        self,
        tasks: list[Task],
        inbound_orders: dict[str, tuple[str, str]],
        outbound_orders: dict[str, tuple[str, str]],
        task_locations: dict[str, str],
        now: datetime,
    ) -> list[dict[str, Any]]:
        items = []
        for task in tasks:
            operation, action_route, action_key = _task_route(task.task_type)
            reference_number = None
            client_id = None
            if task.reference_type == "inbound_order" and task.reference_id:
                reference_number, client_id = inbound_orders.get(task.reference_id, (None, None))
            elif task.reference_type == "outbound_order" and task.reference_id:
                reference_number, client_id = outbound_orders.get(task.reference_id, (None, None))
            blocked = task.status == TaskStatus.FAILED.value
            items.append(
                {
                    "id": f"task:{task.id}",
                    "category": "task",
                    "operation": operation,
                    "lane": _lane(due_at=None, now=now, active=not blocked, blocked=blocked),
                    "source_status": task.status,
                    "reference_type": task.reference_type or "task",
                    "reference_id": task.reference_id or task.id,
                    "reference_number": reference_number or task.id[:8],
                    "client_id": client_id,
                    "priority": int(task.priority or 5),
                    "due_at": None,
                    "created_at": _iso(task.created_at),
                    "quantity": int(task.quantity or 0),
                    "quantity_progress": None,
                    "location_label": self._task_location_label(task, task_locations),
                    "client_name": None,
                    "assigned_type": task.assigned_type,
                    "assigned_to": task.assigned_to,
                    "action_key": action_key,
                    "action_route": action_route,
                    "blocker_code": "task_failed" if blocked else None,
                }
            )
        return items

    @staticmethod
    def _task_location_label(task: Task, task_locations: dict[str, str]) -> str | None:
        source = task_locations.get(task.source_location_id) if task.source_location_id else None
        destination = (
            task_locations.get(task.destination_location_id)
            if task.destination_location_id
            else None
        )
        if source and destination:
            return f"{source} -> {destination}"
        return source or destination

    @staticmethod
    def _sort_key(item: dict[str, Any], now: datetime) -> tuple[int, int, datetime, str]:
        lane_rank = {"blocked": 0, "delayed": 1, "now": 2, "next": 3}
        due = _aware(datetime.fromisoformat(item["due_at"])) if item.get("due_at") else None
        return (
            lane_rank.get(item["lane"], 4),
            int(item.get("priority") or 5),
            due or now,
            str(item.get("id") or ""),
        )
