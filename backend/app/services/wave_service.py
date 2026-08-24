"""
Wave Management Service — batch orders into waves for efficient picking.

Wave: a group of orders processed together. Orders are grouped by:
- Carrier (all UPS Ground orders in one wave)
- Cutoff time (orders that must ship today)
- Client (all orders for one cargo owner)
- Zone (all picks from Zone A)

Batch picking: one picker walks the warehouse once for multiple orders,
picking all items into a cart, then sorts at pack station.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import generate_uuid
from app.models.inventory import Inventory
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.models.task import AssignedType, PickAllocation, Task, TaskStatus, TaskType
from app.models.warehouse import Location
from app.services.outbound_readiness import apply_outbound_readiness_projection


class WaveService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def _record_pick_allocation(
        self,
        line: OutboundOrderLine,
        warehouse_id: str,
        location_id: str,
        quantity: int,
    ) -> None:
        existing = await self.db.scalar(
            select(PickAllocation).where(
                PickAllocation.tenant_id == self.tenant_id,
                PickAllocation.order_id == line.order_id,
                PickAllocation.order_line_id == line.id,
                PickAllocation.location_id == location_id,
                PickAllocation.task_id.is_(None),
            )
        )
        if existing:
            existing.quantity += quantity
            return

        self.db.add(
            PickAllocation(
                tenant_id=self.tenant_id,
                order_id=line.order_id,
                order_line_id=line.id,
                warehouse_id=warehouse_id,
                sku_id=line.sku_id,
                location_id=location_id,
                quantity=quantity,
            )
        )

    async def create_wave(
        self,
        warehouse_id: str,
        order_ids: list[str] | None = None,
        group_by: str = "all",  # all | carrier | client
        max_orders: int = 50,
    ) -> dict:
        """
        Create a wave from pending orders. Groups orders and generates
        consolidated pick tasks sorted by pick path.

        Returns wave summary with task counts.
        """
        # Find eligible orders
        query = select(OutboundOrder).where(
            OutboundOrder.warehouse_id == warehouse_id,
            OutboundOrder.status == OutboundStatus.PENDING.value,
        )

        if order_ids:
            query = query.where(OutboundOrder.id.in_(order_ids))

        query = query.order_by(OutboundOrder.priority, OutboundOrder.created_at).limit(max_orders)
        result = await self.db.execute(query)
        orders = list(result.scalars())

        if not orders:
            return {"success": False, "error": "No pending orders found"}

        # Group orders
        groups: dict[str, list[OutboundOrder]] = {}
        for order in orders:
            if group_by == "carrier":
                key = order.carrier or "unassigned"
            elif group_by == "client":
                key = order.client_id
            else:
                key = "all"
            groups.setdefault(key, []).append(order)

        wave_id = generate_uuid()[:8]
        total_tasks = 0
        total_orders = 0
        allocation_results = []

        for _group_key, group_orders in groups.items():
            # Allocate inventory for each order
            for order in group_orders:
                alloc = await self._allocate_order(order)
                allocation_results.append(alloc)
                if alloc["fully_allocated"]:
                    order.status = OutboundStatus.ALLOCATED.value
                    apply_outbound_readiness_projection(order)
                    total_orders += 1

            # Generate consolidated pick tasks
            # Merge picks for same SKU+location across orders in this group
            pick_map: dict[tuple, dict] = {}  # (location_id, sku_id) → {qty, order_ids}

            for order in group_orders:
                if order.status != OutboundStatus.ALLOCATED.value:
                    continue

                allocation_result = await self.db.execute(
                    select(PickAllocation).where(
                        PickAllocation.tenant_id == self.tenant_id,
                        PickAllocation.order_id == order.id,
                        PickAllocation.quantity > PickAllocation.quantity_picked,
                    )
                )
                allocations = allocation_result.scalars().all()
                if allocations:
                    for allocation in allocations:
                        key = (allocation.location_id, allocation.sku_id)
                        if key not in pick_map:
                            pick_map[key] = {"qty": 0, "order_ids": [], "allocation_ids": []}
                        pick_map[key]["qty"] += allocation.quantity - allocation.quantity_picked
                        pick_map[key]["allocation_ids"].append(allocation.id)
                        if order.id not in pick_map[key]["order_ids"]:
                            pick_map[key]["order_ids"].append(order.id)
                else:
                    lines_result = await self.db.execute(
                        select(OutboundOrderLine).where(
                            OutboundOrderLine.order_id == order.id,
                            OutboundOrderLine.quantity_allocated > 0,
                        )
                    )
                    for line in lines_result.scalars():
                        if not line.pick_location_id:
                            continue
                        key = (line.pick_location_id, line.sku_id)
                        if key not in pick_map:
                            pick_map[key] = {"qty": 0, "order_ids": [], "allocation_ids": []}
                        pick_map[key]["qty"] += line.quantity_allocated
                        if order.id not in pick_map[key]["order_ids"]:
                            pick_map[key]["order_ids"].append(order.id)

                order.status = OutboundStatus.PICKING.value
                apply_outbound_readiness_projection(order)

            # Create tasks sorted by pick_sequence (path optimization)
            for (location_id, sku_id), info in pick_map.items():
                loc_result = await self.db.execute(
                    select(Location.pick_sequence).where(Location.id == location_id)
                )
                loc_result.scalar() or 999

                task = Task(
                    tenant_id=self.tenant_id,
                    warehouse_id=warehouse_id,
                    task_type=TaskType.PICK.value,
                    status=TaskStatus.PENDING.value,
                    priority=3,
                    sku_id=sku_id,
                    quantity=info["qty"],
                    source_location_id=location_id,
                    reference_type="wave",
                    reference_id=f"wave-{wave_id}",
                    assigned_type=AssignedType.UNASSIGNED.value,
                )
                self.db.add(task)
                await self.db.flush()
                if info["allocation_ids"]:
                    allocation_update = await self.db.execute(
                        select(PickAllocation).where(PickAllocation.id.in_(info["allocation_ids"]))
                    )
                    for allocation in allocation_update.scalars():
                        allocation.task_id = task.id
                total_tasks += 1

        await self.db.flush()

        return {
            "success": True,
            "wave_id": f"wave-{wave_id}",
            "orders_count": total_orders,
            "tasks_count": total_tasks,
            "groups": len(groups),
            "group_by": group_by,
            "allocations": allocation_results,
        }

    async def _allocate_order(self, order: OutboundOrder) -> dict:
        """Allocate inventory for a single order (FIFO)."""
        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(OutboundOrderLine.order_id == order.id)
        )
        lines = lines_result.scalars().all()
        fully = True

        for line in lines:
            needed = line.quantity_ordered - line.quantity_allocated
            if needed <= 0:
                continue

            inv_result = await self.db.execute(
                select(Inventory)
                .where(
                    Inventory.warehouse_id == order.warehouse_id,
                    Inventory.sku_id == line.sku_id,
                    (
                        Inventory.quantity_on_hand
                        - Inventory.quantity_allocated
                        - Inventory.quantity_damaged
                    )
                    > 0,
                )
                .order_by(Inventory.received_at.asc().nulls_last())
            )

            allocated = 0
            for inv in inv_result.scalars():
                if allocated >= needed:
                    break
                available = inv.quantity_on_hand - inv.quantity_allocated - inv.quantity_damaged
                take = min(available, needed - allocated)
                inv.quantity_allocated += take
                allocated += take
                await self._record_pick_allocation(line, order.warehouse_id, inv.location_id, take)
                if not line.pick_location_id:
                    line.pick_location_id = inv.location_id

            line.quantity_allocated += allocated
            if allocated < needed:
                fully = False

        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "fully_allocated": fully,
        }

    async def get_wave_progress(self, wave_id: str) -> dict:
        """Get progress of a wave — how many tasks completed."""
        result = await self.db.execute(
            select(
                Task.status,
                func.count(Task.id),
            )
            .where(
                Task.reference_id == wave_id,
                Task.reference_type == "wave",
            )
            .group_by(Task.status)
        )
        status_counts = {row[0]: row[1] for row in result.all()}
        total = sum(status_counts.values())
        completed = status_counts.get(TaskStatus.COMPLETED.value, 0)

        return {
            "wave_id": wave_id,
            "total_tasks": total,
            "completed": completed,
            "in_progress": status_counts.get(TaskStatus.IN_PROGRESS.value, 0),
            "pending": status_counts.get(TaskStatus.PENDING.value, 0),
            "progress_pct": round(completed / max(total, 1) * 100),
        }
