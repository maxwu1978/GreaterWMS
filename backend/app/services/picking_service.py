"""
Picking Service — order allocation, wave picking, and path optimization.

Flow: Outbound order → Allocate inventory → Create pick tasks → Operator picks → Confirm

Allocation strategies:
- FEFO (First Expired, First Out) — for perishable goods
- FIFO (First In, First Out) — default
- Zone-based — pick from nearest zone first
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import for_update
from app.models.inventory import Inventory, TransactionType
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.models.task import AssignedType, PickAllocation, Task, TaskStatus, TaskType
from app.models.warehouse import Location
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import post_movement
from app.services.outbound_readiness import (
    apply_outbound_readiness_projection,
    pick_readiness_from_summary,
)

_PICK_CONFIRM = AgentGateSpec(
    action="picking.confirm",
    risk="medium",
    permission="fulfillment.execute",
    entity_type="pick_task",
    token_prefix="pick-confirm",
)

_PICK_SHORT = AgentGateSpec(
    action="picking.short",
    risk="medium",
    permission="fulfillment.execute",
    entity_type="pick_task",
    token_prefix="pick-short",
)


class PickingService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def _failure(self, error_code: str, error: str, task_id: str) -> dict:
        return {
            "success": False,
            "error_code": error_code,
            "error": error,
            "detail": {"error_code": error_code, "message": error},
            "task_id": task_id,
        }

    def _http_error(self, status_code: int, error_code: str, message: str) -> HTTPException:
        return HTTPException(
            status_code=status_code,
            detail={"error_code": error_code, "message": message},
        )

    async def _get_order(self, order_id: str) -> OutboundOrder:
        order = await self.db.scalar(
            select(OutboundOrder).where(
                OutboundOrder.id == order_id,
                OutboundOrder.tenant_id == self.tenant_id,
            )
        )
        if not order:
            raise self._http_error(
                status.HTTP_404_NOT_FOUND,
                "outbound_order_not_found",
                "Outbound order not found",
            )
        return order

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

    async def allocate_order(self, order_id: str) -> dict:
        """
        Allocate inventory to an outbound order.
        Uses FIFO by default (oldest received_at first).
        For SKUs with requires_expiry, uses FEFO (earliest expiry_date first).

        Returns allocation result with any shortages.
        """
        order = await self._get_order(order_id)
        if order.status != OutboundStatus.PENDING.value:
            raise self._http_error(
                status_code=status.HTTP_409_CONFLICT,
                error_code="pick_allocate_order_not_pending",
                message=(
                    "Only pending outbound orders can be allocated. "
                    f"This outbound order is currently {order.status}."
                ),
            )

        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        lines = lines_result.scalars().all()

        allocation_results = []
        fully_allocated = True

        for line in lines:
            allocated = await self._allocate_line(line, order.warehouse_id)
            allocation_results.append(allocated)
            if allocated["shortage"] > 0:
                fully_allocated = False

        order.status = (
            OutboundStatus.ALLOCATED.value if fully_allocated else OutboundStatus.PENDING.value
        )
        total_items = sum(line.quantity_ordered or 0 for line in lines)
        shortage_units = sum(result["shortage"] for result in allocation_results)
        apply_outbound_readiness_projection(
            order,
            pick_readiness=pick_readiness_from_summary(
                order.status,
                total_items,
                shortage_units,
            ),
        )
        await self.db.flush()

        return {
            "order_id": order_id,
            "fully_allocated": fully_allocated,
            "lines": allocation_results,
        }

    async def _allocate_line(self, line: OutboundOrderLine, warehouse_id: str) -> dict:
        """Allocate inventory for a single order line using FIFO."""
        needed = line.quantity_ordered - line.quantity_allocated

        if needed <= 0:
            return {"sku_id": line.sku_id, "allocated": line.quantity_allocated, "shortage": 0}

        # Find available inventory, ordered by received_at (FIFO)
        result = await self.db.execute(
            for_update(
                select(Inventory)
                .where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.warehouse_id == warehouse_id,
                    Inventory.sku_id == line.sku_id,
                    (
                        Inventory.quantity_on_hand
                        - Inventory.quantity_allocated
                        - Inventory.quantity_damaged
                    )
                    > 0,
                )
                .order_by(
                    asc(Inventory.expiry_date).nulls_last(),
                    asc(Inventory.received_at),
                )
            )
        )
        inventory_rows = result.scalars().all()

        total_allocated = 0
        pick_locations = []

        for inv in inventory_rows:
            if total_allocated >= needed:
                break

            available = inv.quantity_on_hand - inv.quantity_allocated - inv.quantity_damaged
            to_allocate = min(available, needed - total_allocated)

            inv.quantity_allocated += to_allocate
            total_allocated += to_allocate

            pick_locations.append(
                {
                    "location_id": inv.location_id,
                    "quantity": to_allocate,
                    "lot_number": inv.lot_number,
                }
            )
            await self._record_pick_allocation(line, warehouse_id, inv.location_id, to_allocate)

        line.quantity_allocated = line.quantity_allocated + total_allocated
        if pick_locations:
            line.pick_location_id = pick_locations[0]["location_id"]

        return {
            "sku_id": line.sku_id,
            "needed": needed,
            "allocated": total_allocated,
            "shortage": max(0, needed - total_allocated),
            "pick_locations": pick_locations,
        }

    async def create_pick_tasks(self, order_id: str) -> list[str]:
        """
        Generate pick tasks for an allocated order.
        One task per location-SKU combination.
        Tasks are ordered by pick_sequence for path optimization.
        """
        order = await self._get_order(order_id)
        if order.status != OutboundStatus.ALLOCATED.value:
            raise self._http_error(
                status_code=status.HTTP_409_CONFLICT,
                error_code="pick_release_order_not_allocated",
                message=(
                    "Only allocated outbound orders can be released to pick tasks. "
                    f"This outbound order is currently {order.status}."
                ),
            )
        existing_task_id = await self.db.scalar(
            select(Task.id).where(
                Task.tenant_id == self.tenant_id,
                Task.task_type == TaskType.PICK.value,
                Task.reference_type == "outbound_order",
                Task.reference_id == order_id,
                Task.status != TaskStatus.CANCELLED.value,
            )
        )
        if existing_task_id:
            raise self._http_error(
                status_code=status.HTTP_409_CONFLICT,
                error_code="pick_tasks_already_released",
                message="This outbound order already has pick tasks.",
            )
        order.status = OutboundStatus.PICKING.value

        task_ids = []
        allocation_result = await self.db.execute(
            select(PickAllocation)
            .join(Location, Location.id == PickAllocation.location_id)
            .where(
                PickAllocation.tenant_id == self.tenant_id,
                PickAllocation.order_id == order_id,
                PickAllocation.quantity > PickAllocation.quantity_picked,
            )
            .order_by(Location.pick_sequence.asc(), PickAllocation.created_at.asc())
        )
        allocations = allocation_result.scalars().all()

        if allocations:
            for allocation in allocations:
                remaining_quantity = allocation.quantity - allocation.quantity_picked
                if remaining_quantity <= 0:
                    continue

                task = Task(
                    tenant_id=self.tenant_id,
                    warehouse_id=order.warehouse_id,
                    task_type=TaskType.PICK.value,
                    status=TaskStatus.PENDING.value,
                    priority=order.priority,
                    sku_id=allocation.sku_id,
                    quantity=remaining_quantity,
                    source_location_id=allocation.location_id,
                    reference_type="outbound_order",
                    reference_id=order_id,
                    assigned_type=AssignedType.UNASSIGNED.value,
                )
                self.db.add(task)
                await self.db.flush()
                allocation.task_id = task.id
                task_ids.append(task.id)
            apply_outbound_readiness_projection(order)
            await self.db.flush()
            return task_ids

        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
                OutboundOrderLine.quantity_allocated > 0,
            )
        )
        lines = lines_result.scalars().all()

        for line in lines:
            if not line.pick_location_id:
                continue

            task = Task(
                tenant_id=self.tenant_id,
                warehouse_id=order.warehouse_id,
                task_type=TaskType.PICK.value,
                status=TaskStatus.PENDING.value,
                priority=order.priority,
                sku_id=line.sku_id,
                quantity=line.quantity_allocated,
                source_location_id=line.pick_location_id,
                reference_type="outbound_order",
                reference_id=order_id,
                assigned_type=AssignedType.UNASSIGNED.value,
            )
            self.db.add(task)
            await self.db.flush()
            task_ids.append(task.id)

        apply_outbound_readiness_projection(order)
        await self.db.flush()
        return task_ids

    async def confirm_pick(
        self,
        task_id: str,
        quantity_picked: int,
        user_id: str,
    ) -> dict:
        """
        Operator confirms pick — scanned SKU barcode and quantity at location.
        Deducts inventory and records the transaction.

        Concurrency safety:
        - Task locked with FOR UPDATE to prevent double-confirm
        - Task status checked: only PENDING/ASSIGNED/IN_PROGRESS can be confirmed
        - Inventory locked with FOR UPDATE to prevent negative stock
        - Available quantity validated before deduction
        """
        # Lock task row to prevent double-confirm
        result = await self.db.execute(
            for_update(
                select(Task).where(
                    Task.id == task_id,
                    Task.tenant_id == self.tenant_id,
                    Task.task_type == TaskType.PICK.value,
                )
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            return self._failure("pick_task_not_found", "Pick task was not found", task_id)

        # Guard: quantity must be positive
        if quantity_picked <= 0:
            return self._failure(
                "pick_quantity_non_positive",
                "quantity_picked must be greater than 0",
                task_id,
            )

        # Guard: quantity must not exceed what the task requires
        if quantity_picked > task.quantity:
            return self._failure(
                "pick_quantity_exceeds_task",
                f"quantity_picked ({quantity_picked}) exceeds task quantity ({task.quantity})",
                task_id,
            )

        # Guard: only confirm tasks that haven't been completed yet
        if task.status == TaskStatus.COMPLETED.value:
            return self._failure("pick_task_already_completed", "Task already completed", task_id)
        if task.status == TaskStatus.CANCELLED.value:
            return self._failure("pick_task_cancelled", "Task is cancelled", task_id)
        if task.assigned_type == AssignedType.AGV.value:
            return self._failure(
                "pick_task_assigned_to_agv",
                "Task is assigned to AGV work and cannot be confirmed by a human operator",
                task_id,
            )
        if (
            task.assigned_type == AssignedType.HUMAN.value
            and task.assigned_to
            and task.assigned_to != user_id
        ):
            return self._failure(
                "pick_task_assigned_to_other_operator",
                "Task is assigned to another operator",
                task_id,
            )

        allocation_result = await self.db.execute(
            select(PickAllocation)
            .where(
                PickAllocation.tenant_id == self.tenant_id,
                PickAllocation.task_id == task.id,
            )
            .order_by(PickAllocation.created_at.asc())
        )
        pick_allocations = allocation_result.scalars().all()
        allocation_remaining = sum(
            max(0, allocation.quantity - allocation.quantity_picked)
            for allocation in pick_allocations
        )
        if pick_allocations and quantity_picked > allocation_remaining:
            return self._failure(
                "pick_quantity_exceeds_reserved",
                (
                    f"quantity_picked ({quantity_picked}) exceeds reserved quantity "
                    f"({allocation_remaining})"
                ),
                task_id,
            )

        # Lock inventory row to prevent concurrent deductions
        inv_result = await self.db.execute(
            for_update(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == task.source_location_id,
                    Inventory.sku_id == task.sku_id,
                )
            )
        )
        inv = inv_result.scalar_one_or_none()
        if not inv:
            return self._failure(
                "pick_source_inventory_not_found",
                "Source inventory was not found for this pick task",
                task_id,
            )

        # Validate: don't let quantity go negative
        if inv.quantity_on_hand < quantity_picked:
            return self._failure(
                "pick_insufficient_stock",
                f"Insufficient stock: {inv.quantity_on_hand} on hand, tried to pick {quantity_picked}",
                task_id,
            )

        # Deduct picked quantity and record the transaction
        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=inv.client_id,
            transaction_type=TransactionType.PICK.value,
            sku_id=task.sku_id,
            location_id=task.source_location_id,
            quantity_change=-quantity_picked,
            inventory=inv,
            delta_on_hand=-quantity_picked,
            delta_allocated=-max(0, min(quantity_picked, inv.quantity_allocated)),
            from_location_id=task.source_location_id,
            reference_type="outbound_order",
            reference_id=task.reference_id,
            performed_by=user_id,
            flush=False,
        )

        # Update task
        task.status = TaskStatus.COMPLETED.value
        task.assigned_to = user_id
        task.assigned_type = AssignedType.HUMAN.value
        task.completed_at = datetime.now(UTC)

        # Update order line
        affected_order_ids: set[str] = set()
        if pick_allocations:
            remaining_to_apply = quantity_picked
            for allocation in pick_allocations:
                if remaining_to_apply <= 0:
                    break
                allocation_open = max(0, allocation.quantity - allocation.quantity_picked)
                applied_quantity = min(allocation_open, remaining_to_apply)
                if applied_quantity <= 0:
                    continue

                allocation.quantity_picked += applied_quantity
                affected_order_ids.add(allocation.order_id)
                remaining_to_apply -= applied_quantity

                line = await self.db.scalar(
                    select(OutboundOrderLine).where(
                        OutboundOrderLine.tenant_id == self.tenant_id,
                        OutboundOrderLine.id == allocation.order_line_id,
                    )
                )
                if line:
                    line.quantity_picked += applied_quantity
        elif task.reference_id:
            line_result = await self.db.execute(
                select(OutboundOrderLine).where(
                    OutboundOrderLine.tenant_id == self.tenant_id,
                    OutboundOrderLine.order_id == task.reference_id,
                    OutboundOrderLine.sku_id == task.sku_id,
                )
            )
            line = line_result.scalar_one_or_none()
            if line:
                line.quantity_picked += quantity_picked

        # Check if all picks for this order are done (only for outbound_order tasks, not wave tasks)
        if affected_order_ids:
            for order_id in affected_order_ids:
                await self._mark_order_picked_if_lines_complete(order_id)
        elif task.reference_type == "outbound_order" and task.reference_id:
            await self._check_picking_complete(task.reference_id)

        await self.db.flush()
        return {
            "success": True,
            "task_id": task_id,
            "picked": quantity_picked,
            "remaining_at_location": inv.quantity_on_hand,
        }

    async def preview_pick_confirmation(
        self,
        task_id: str,
        quantity_picked: int,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"task_id": task_id, "quantity_picked": quantity_picked}
        endpoint = "POST /api/v1/fulfillment/pick/confirm"
        entity = {"type": "pick_task", "id": task_id, "task_id": task_id}
        state_before = await self._pick_state(task_id)
        planned_result, state_after = await agent_preview.savepoint_dry_run(
            self.db,
            lambda: self.confirm_pick(
                task_id=task_id,
                quantity_picked=quantity_picked,
                user_id=user_id or "agent-preview",
            ),
            lambda: self._pick_state(task_id),
        )

        if not planned_result.get("success"):
            return agent_preview.blocked_preview(
                _PICK_CONFIRM,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="recover_or_choose_next_pick_task",
                result={
                    "what_happened": planned_result.get("error") or "Pick cannot be confirmed.",
                    "why_blocked": planned_result.get("error_code") or "pick_preview_failed",
                    "recommended_action": "Review the task, picked quantity, source stock, and recovery path.",
                    "safe_commands": [
                        "wms picking next --dry-run --live-preview",
                        "wms picking short --dry-run --task-id TASK --reason REASON",
                    ],
                },
            )

        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _PICK_CONFIRM,
            entity=entity,
            entity_id=task_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"task_id": task_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "task_id": task_id,
                "order_id": state_before.get("reference_id"),
            },
            records=[
                {
                    "type": "pick_task",
                    "id": task_id,
                    "sku_id": state_before.get("sku_id"),
                    "quantity": state_before.get("quantity"),
                    "quantity_picked": quantity_picked,
                    "source_location_id": state_before.get("source_location_id"),
                }
            ],
            impact={
                "task_status": "completed",
                "picked_quantity": quantity_picked,
                "remaining_at_location": planned_result.get("remaining_at_location"),
            },
            result={
                "message": "No backend write was performed.",
                "planned_result": planned_result,
                "safe_commands": [
                    "wms picking confirm --dry-run --live-preview",
                    "wms picking next --dry-run --live-preview",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_pick_with_token(
        self,
        task_id: str,
        quantity_picked: int,
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _PICK_CONFIRM,
            confirmation_token,
            message="A picking confirmation token is required before the agent can write.",
        )

        preview = await self.preview_pick_confirmation(
            task_id=task_id,
            quantity_picked=quantity_picked,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _PICK_CONFIRM,
            preview,
            error_code="pick_preview_failed",
            default_message="Pick preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _PICK_CONFIRM,
            entity_id=task_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The picking confirmation token no longer matches the current preview.",
        )

        result = await self.confirm_pick(
            task_id=task_id,
            quantity_picked=quantity_picked,
            user_id=user_id,
        )
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _PICK_CONFIRM,
            evidence=evidence,
            ok=bool(result.get("success")),
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._pick_state(task_id),
            payload_hash=payload_hash,
            next_action="choose_next_pick_task_or_continue_to_shipping",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=result.get("error") or result.get("error_code"),
        )

    async def preview_pick_short(
        self,
        task_id: str,
        quantity_available: int,
        reason: str,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {
            "task_id": task_id,
            "quantity_available": quantity_available,
            "reason": reason,
        }
        endpoint = "POST /api/v1/fulfillment/pick/short"
        entity = {"type": "pick_task", "id": task_id, "task_id": task_id}
        state_before = await self._pick_state(task_id)
        if not reason.strip():
            return agent_preview.blocked_preview(
                _PICK_SHORT,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="provide_short_reason",
                result={
                    "what_happened": "Pick shortage needs a reason.",
                    "why_blocked": "pick_short_reason_required",
                    "recommended_action": "Add a shortage reason before previewing again.",
                    "safe_commands": ["wms picking short --dry-run --reason REASON"],
                },
            )

        planned_result, state_after = await agent_preview.savepoint_dry_run(
            self.db,
            lambda: self.confirm_pick(
                task_id=task_id,
                quantity_picked=quantity_available,
                user_id=user_id or "agent-preview",
            ),
            lambda: self._pick_state(task_id),
        )

        if not planned_result.get("success"):
            return agent_preview.blocked_preview(
                _PICK_SHORT,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="recover_or_choose_next_pick_task",
                result={
                    "what_happened": planned_result.get("error") or "Pick short cannot be recorded.",
                    "why_blocked": planned_result.get("error_code") or "pick_short_preview_failed",
                    "recommended_action": "Review available quantity, task state, and shortage reason.",
                    "safe_commands": [
                        "wms picking next --dry-run --live-preview",
                        "wms picking confirm --dry-run --task-id TASK --quantity QTY",
                    ],
                },
            )

        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _PICK_SHORT,
            entity=entity,
            entity_id=task_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"task_id": task_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "task_id": task_id,
                "order_id": state_before.get("reference_id"),
            },
            records=[
                {
                    "type": "pick_task",
                    "id": task_id,
                    "sku_id": state_before.get("sku_id"),
                    "requested_quantity": state_before.get("quantity"),
                    "quantity_available": quantity_available,
                    "short_reason": reason,
                }
            ],
            impact={
                "task_status": "completed",
                "picked_quantity": quantity_available,
                "short_quantity": max(0, int(state_before.get("quantity") or 0) - quantity_available),
            },
            result={
                "message": "No backend write was performed.",
                "planned_result": planned_result,
                "safe_commands": [
                    "wms picking short --dry-run --live-preview",
                    "wms picking next --dry-run --live-preview",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_pick_short_with_token(
        self,
        task_id: str,
        quantity_available: int,
        reason: str,
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _PICK_SHORT,
            confirmation_token,
            message="A picking short token is required before the agent can write.",
        )

        preview = await self.preview_pick_short(
            task_id=task_id,
            quantity_available=quantity_available,
            reason=reason,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _PICK_SHORT,
            preview,
            error_code="pick_short_preview_failed",
            default_message="Pick short preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _PICK_SHORT,
            entity_id=task_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The picking short token no longer matches the current preview.",
        )

        result = await self.confirm_pick(
            task_id=task_id,
            quantity_picked=quantity_available,
            user_id=user_id,
        )
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _PICK_SHORT,
            evidence=evidence,
            ok=bool(result.get("success")),
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._pick_state(task_id),
            payload_hash=payload_hash,
            next_action="review_shortage_or_continue_to_shipping",
            result={**result, "short_reason": reason},
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=result.get("error") or result.get("error_code"),
        )

    async def _pick_state(self, task_id: str) -> dict:
        task = await self.db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == self.tenant_id,
                Task.task_type == TaskType.PICK.value,
            )
        )
        if not task:
            return {"task_id": task_id, "task_status": "not_found"}

        inventory = None
        if task.source_location_id and task.sku_id:
            inventory = await self.db.scalar(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == task.source_location_id,
                    Inventory.sku_id == task.sku_id,
                )
            )
        allocations = (
            await self.db.execute(
                select(PickAllocation)
                .where(
                    PickAllocation.tenant_id == self.tenant_id,
                    PickAllocation.task_id == task.id,
                )
                .order_by(PickAllocation.created_at.asc())
            )
        ).scalars().all()
        return {
            "task_id": task.id,
            "task_status": task.status,
            "warehouse_id": task.warehouse_id,
            "sku_id": task.sku_id,
            "quantity": task.quantity,
            "source_location_id": task.source_location_id,
            "reference_type": task.reference_type,
            "reference_id": task.reference_id,
            "assigned_type": task.assigned_type,
            "assigned_to": task.assigned_to,
            "inventory": {
                "id": inventory.id,
                "quantity_on_hand": inventory.quantity_on_hand,
                "quantity_allocated": inventory.quantity_allocated,
            }
            if inventory
            else None,
            "allocations": [
                {
                    "id": allocation.id,
                    "order_id": allocation.order_id,
                    "order_line_id": allocation.order_line_id,
                    "location_id": allocation.location_id,
                    "quantity": allocation.quantity,
                    "quantity_picked": allocation.quantity_picked,
                }
                for allocation in allocations
            ],
        }

    async def _mark_order_picked_if_lines_complete(self, order_id: str) -> None:
        """Advance an outbound order when every allocated line has been picked."""
        order = await self.db.scalar(
            select(OutboundOrder).where(
                OutboundOrder.id == order_id,
                OutboundOrder.tenant_id == self.tenant_id,
            )
        )
        if not order:
            return

        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        lines = lines_result.scalars().all()
        if lines and all(line.quantity_picked >= line.quantity_ordered for line in lines):
            order.status = OutboundStatus.PICKED.value
            apply_outbound_readiness_projection(order)

    async def _check_picking_complete(self, order_id: str) -> None:
        """If all pick tasks are done, advance order to PICKED status."""
        result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.reference_type == "outbound_order",
                Task.reference_id == order_id,
                Task.tenant_id == self.tenant_id,
                Task.task_type == TaskType.PICK.value,
                Task.status != TaskStatus.COMPLETED.value,
                Task.status != TaskStatus.CANCELLED.value,
            )
        )
        remaining = result.scalar()
        if remaining == 0:
            order_result = await self.db.execute(
                select(OutboundOrder).where(
                    OutboundOrder.id == order_id,
                    OutboundOrder.tenant_id == self.tenant_id,
                )
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.status = OutboundStatus.PICKED.value
                apply_outbound_readiness_projection(order)
