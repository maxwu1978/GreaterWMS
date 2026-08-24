"""
Putaway Service — moves received goods from staging to storage locations.

Flow: Putaway task created → System suggests location → Operator scans & confirms → Inventory moved

Location suggestion strategies:
1. Same SKU consolidation — put near existing stock of the same SKU
2. Zone-based rules — hazmat to hazmat zone, cold to cold zone
3. ABC velocity — fast movers near shipping dock
4. Empty location — find nearest available empty location
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory, TransactionType
from app.models.order import (
    HandlingUnit,
    InboundOrder,
    InboundPackage,
    InboundPackageStatus,
    InboundStatus,
)
from app.models.task import AssignedType, PutawayAllocation, Task, TaskStatus, TaskType
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import StockDelta, ensure_inventory, post_movement

# Putaway reports gate errors under "code" (not "error_code") — keep that shape.
_PUTAWAY_CONFIRM = AgentGateSpec(
    action="putaway.confirm",
    risk="medium",
    permission="fulfillment.execute",
    entity_type="putaway_task",
    token_prefix="put-confirm",
    error_code_key="code",
)


def _slot_policy(value: object, default: str) -> str:
    policy = str(value or default).lower()
    return policy if policy in {"block", "warn", "allow"} else default


class PutawayService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def _failure(self, error_code: str, error: str) -> dict:
        return {"success": False, "error_code": error_code, "error": error}

    def _putaway_error(self, status_code: int, code: str, message: str) -> HTTPException:
        return HTTPException(status_code=status_code, detail={"code": code, "message": message})

    async def suggest_location(
        self,
        warehouse_id: str,
        sku_id: str,
        quantity: int,
        exclude_location_id: str | None = None,
    ) -> list[dict]:
        """
        Suggest putaway locations ranked by priority:
        1. Location already holding same SKU (consolidation)
        2. Empty locations in the same zone
        3. Any available location

        Returns up to 3 suggestions with reason.
        """
        suggestions: list[dict] = []
        planner_rules = await self._get_planner_rules(warehouse_id)

        # Strategy 1: Consolidate with existing SKU inventory
        result = await self.db.execute(
            select(Inventory.location_id, Location.barcode, Location.aisle, Location.rack)
            .join(Location, Location.id == Inventory.location_id)
            .where(
                Inventory.tenant_id == self.tenant_id,
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.quantity_on_hand > 0,
                Location.location_type == LocationType.STORAGE.value,
                Location.current_status != LocationStatus.BLOCKED.value,
                *([Location.id != exclude_location_id] if exclude_location_id else []),
            )
            .limit(1)
        )
        existing = result.first()
        if existing:
            suggestions.append(
                {
                    "location_id": existing.location_id,
                    "barcode": existing.barcode,
                    "address": f"{existing.aisle}-{existing.rack}",
                    "reason": "consolidate_with_existing_sku",
                }
            )

        # Strategy 2: Empty available locations sorted by pick_sequence (nearest to dock)
        attrs: dict = {}
        weight_kg = None
        from app.models.inventory import SKU

        sku_row = await self.db.execute(select(SKU).where(SKU.id == sku_id))
        sku = sku_row.scalar_one_or_none()
        if sku:
            attrs = sku.attributes or {}
            weight_kg = float(sku.weight_kg) if sku.weight_kg else None

        velocity = str(attrs.get("velocity", "")).lower()
        is_fast = attrs.get("fast_mover") is True or velocity in {"a", "fast"}
        is_slow = attrs.get("slow_mover") is True or velocity in {"c", "slow"}
        threshold = float(planner_rules.get("heavy_item_threshold_kg", 20.0))
        is_heavy = bool(weight_kg and weight_kg >= threshold)

        query = select(Location).where(
            Location.tenant_id == self.tenant_id,
            Location.warehouse_id == warehouse_id,
            Location.current_status == LocationStatus.AVAILABLE.value,
            Location.location_type == LocationType.STORAGE.value,
            *([Location.id != exclude_location_id] if exclude_location_id else []),
        )
        if planner_rules.get("heavy_items_low", True) and is_heavy:
            query = query.order_by(Location.level.asc(), Location.pick_sequence.asc())
        elif planner_rules.get("slow_movers_deep", True) and is_slow:
            query = query.order_by(desc(Location.pick_sequence))
        else:
            query = query.order_by(Location.pick_sequence.asc())

        result = await self.db.execute(query.limit(3 - len(suggestions)))
        for loc in result.scalars():
            reason = "empty_available"
            if planner_rules.get("heavy_items_low", True) and is_heavy:
                reason = "heavy_item_low_level"
            elif planner_rules.get("slow_movers_deep", True) and is_slow:
                reason = "slow_mover_deeper_storage"
            elif planner_rules.get("fast_movers_front", True) and is_fast:
                reason = "fast_mover_front_of_flow"
            suggestions.append(
                {
                    "location_id": loc.id,
                    "barcode": loc.barcode,
                    "address": f"{loc.aisle}-{loc.rack}-{loc.level}-{loc.position}",
                    "reason": reason,
                }
            )
            if len(suggestions) >= 3:
                break

        return suggestions

    async def _get_planner_rules(self, warehouse_id: str) -> dict:
        result = await self.db.execute(
            select(Warehouse.address).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == self.tenant_id,
            )
        )
        address = result.scalar_one_or_none() or {}
        return address.get("_planner_rules", {})

    async def confirm_putaway(
        self,
        task_id: str,
        destination_location_id: str,
        user_id: str,
        allocations: list[dict] | None = None,
    ) -> dict:
        """
        Confirm putaway — operator scanned the destination location barcode.
        Moves inventory from staging to storage, completes the task.
        """
        task = await self.db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == self.tenant_id,
                Task.task_type == TaskType.PUTAWAY.value,
            )
        )
        if not task:
            return self._failure(
                "putaway_task_not_available",
                "Putaway task was not found or is no longer available",
            )
        if task.status != TaskStatus.PENDING.value:
            return self._failure(
                "putaway_task_not_pending",
                f"Putaway task is {task.status}; only pending tasks can be confirmed",
            )
        if not task.sku_id or task.quantity <= 0:
            return self._failure(
                "putaway_task_invalid_quantity",
                "Putaway task is missing SKU or quantity information",
            )

        handling_unit = None
        if task.handling_unit_id:
            handling_unit = await self.db.scalar(
                select(HandlingUnit).where(
                    HandlingUnit.id == task.handling_unit_id,
                    HandlingUnit.tenant_id == self.tenant_id,
                )
            )

        resolved_allocations = allocations or [
            {"location_id": destination_location_id, "quantity": task.quantity}
        ]
        normalized_allocations: list[dict] = []
        total_quantity = 0
        location_totals: dict[str, int] = {}
        for idx, allocation in enumerate(resolved_allocations):
            location_id = allocation.get("location_id")
            quantity = int(allocation.get("quantity") or 0)
            if not location_id:
                return self._failure(
                    "putaway_allocation_missing_destination",
                    "Putaway allocation is missing a destination location",
                )
            if quantity <= 0:
                return self._failure(
                    "putaway_allocation_invalid_quantity",
                    "Putaway allocation quantity must be greater than 0",
                )
            location_totals[location_id] = location_totals.get(location_id, 0) + quantity
            total_quantity += quantity
            normalized_allocations.append(
                {"location_id": location_id, "quantity": quantity, "sort_order": idx}
            )

        if total_quantity != task.quantity:
            return self._failure(
                "putaway_allocation_quantity_mismatch",
                "Putaway allocation quantities must equal the task quantity",
            )

        normalized_allocations = [
            {"location_id": location_id, "quantity": quantity, "sort_order": idx}
            for idx, (location_id, quantity) in enumerate(location_totals.items())
        ]

        destination_ids = list(location_totals.keys())
        destination_result = await self.db.execute(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.id.in_(destination_ids),
            )
        )
        destination_locations = {loc.id: loc for loc in destination_result.scalars()}
        missing_destination_ids = [
            location_id
            for location_id in destination_ids
            if location_id not in destination_locations
        ]
        if missing_destination_ids:
            return self._failure(
                "putaway_destination_not_found",
                "Selected destination location was not found for this warehouse",
            )

        invalid_destinations = [
            loc.barcode
            for loc in destination_locations.values()
            if loc.warehouse_id != task.warehouse_id
            or loc.location_type != LocationType.STORAGE.value
        ]
        if invalid_destinations:
            return self._failure(
                "putaway_destination_not_storage_slot",
                "Selected destination must be a storage slot in the task warehouse",
            )

        blocked_destinations = [
            loc.barcode
            for loc in destination_locations.values()
            if loc.current_status == LocationStatus.BLOCKED.value
        ]
        if blocked_destinations:
            return self._failure(
                "putaway_destination_blocked",
                "Selected destination is blocked and cannot receive putaway stock",
            )

        source_location_id = task.source_location_id or (
            handling_unit.staging_location_id if handling_unit else None
        )
        if source_location_id and not task.source_location_id:
            task.source_location_id = source_location_id
        if not source_location_id:
            return self._failure(
                "putaway_source_staging_missing",
                (
                    "This putaway task has no source staging location. "
                    "Open the receiving record and confirm the staging location before putaway."
                ),
            )

        source_location = await self.db.scalar(
            select(Location).where(
                Location.id == source_location_id,
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == task.warehouse_id,
            )
        )
        if not source_location:
            return self._failure(
                "putaway_source_staging_not_found",
                "Source staging location was not found for this task",
            )

        client_id = None
        if task.reference_type == "inbound_order" and task.reference_id:
            inbound_order = await self.db.scalar(
                select(InboundOrder).where(
                    InboundOrder.id == task.reference_id,
                    InboundOrder.tenant_id == self.tenant_id,
                )
            )
            if inbound_order and inbound_order.status != InboundStatus.PUTAWAY.value:
                return self._failure(
                    "putaway_inbound_not_released",
                    (
                        "Only inbound orders released to putaway can be confirmed from the putaway board. "
                        f"This inbound order is currently {inbound_order.status}."
                    ),
                )
            client_id = inbound_order.client_id if inbound_order else None

        # Find the inventory at staging (source)
        inv_query = select(Inventory).where(
            Inventory.tenant_id == self.tenant_id,
            Inventory.sku_id == task.sku_id,
            Inventory.warehouse_id == task.warehouse_id,
            Inventory.location_id == source_location_id,
            Inventory.quantity_on_hand > 0,
        )
        if client_id:
            inv_query = inv_query.where(Inventory.client_id == client_id)
        if handling_unit and handling_unit.lot_number:
            inv_query = inv_query.where(Inventory.lot_number == handling_unit.lot_number)
        if handling_unit and handling_unit.expiry_date:
            inv_query = inv_query.where(Inventory.expiry_date == handling_unit.expiry_date)

        result = await self.db.execute(inv_query.order_by(desc(Inventory.quantity_on_hand)))
        source_candidates = result.scalars().all()
        source_inv = next(
            (inv for inv in source_candidates if inv.quantity_on_hand >= task.quantity),
            None,
        )

        if not source_inv:
            available_quantity = sum(inv.quantity_on_hand for inv in source_candidates)
            if available_quantity >= task.quantity:
                return self._failure(
                    "putaway_source_stock_split",
                    (
                        "Source stock is split across multiple inventory records. "
                        "Consolidate the staging stock or correct the task source before confirming putaway."
                    ),
                )
            return self._failure(
                "putaway_source_inventory_short",
                (
                    f"Source inventory has {available_quantity} available units, "
                    f"but this putaway task requires {task.quantity}"
                ),
            )

        planner_rules = await self._get_planner_rules(task.warehouse_id)
        allow_same_sku_consolidation = bool(planner_rules.get("allow_same_sku_consolidation", True))
        different_sku_slot_policy = _slot_policy(
            planner_rules.get("different_sku_slot_policy"),
            "block",
        )
        lot_expiry_mismatch_policy = _slot_policy(
            planner_rules.get("lot_expiry_mismatch_policy"),
            "warn",
        )
        placement_warnings: list[str] = []

        destination_inventory_result = await self.db.execute(
            select(Inventory).where(
                Inventory.tenant_id == self.tenant_id,
                Inventory.warehouse_id == task.warehouse_id,
                Inventory.location_id.in_(destination_ids),
                Inventory.quantity_on_hand > 0,
            )
        )
        destination_inventory = destination_inventory_result.scalars().all()
        destination_inventory_by_location: dict[str, list[Inventory]] = {}
        for inv in destination_inventory:
            destination_inventory_by_location.setdefault(inv.location_id, []).append(inv)

        for location_id, existing_rows in destination_inventory_by_location.items():
            destination_barcode = destination_locations[location_id].barcode
            different_sku_rows = [inv for inv in existing_rows if inv.sku_id != task.sku_id]
            if different_sku_rows:
                message = (
                    f"Selected destination {destination_barcode} already contains a different SKU. "
                    "Choose an empty slot or a slot with the same SKU."
                )
                if different_sku_slot_policy == "block":
                    return self._failure("putaway_destination_different_sku", message)
                if different_sku_slot_policy == "warn":
                    placement_warnings.append(message)

            same_sku_rows = [inv for inv in existing_rows if inv.sku_id == task.sku_id]
            if same_sku_rows and not allow_same_sku_consolidation:
                return self._failure(
                    "putaway_destination_same_sku_disabled",
                    (
                        f"Selected destination {destination_barcode} already contains this SKU, "
                        "but same-SKU consolidation is disabled for this warehouse."
                    ),
                )

            mismatched_lot_rows = [
                inv
                for inv in same_sku_rows
                if inv.lot_number != source_inv.lot_number
                or inv.expiry_date != source_inv.expiry_date
            ]
            if mismatched_lot_rows:
                message = (
                    f"Selected destination {destination_barcode} already contains the same SKU "
                    "with a different lot or expiry date."
                )
                if lot_expiry_mismatch_policy == "block":
                    return self._failure("putaway_destination_lot_expiry_mismatch", message)
                if lot_expiry_mismatch_policy == "warn":
                    placement_warnings.append(message)

        allocation_results: list[dict] = []
        source_deducted = False
        for allocation in normalized_allocations:
            dest_result = await self.db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == allocation["location_id"],
                    Inventory.sku_id == task.sku_id,
                )
            )
            dest_candidates = dest_result.scalars().all()
            dest_inv = next(
                (
                    inv
                    for inv in dest_candidates
                    if inv.client_id == source_inv.client_id
                    and inv.lot_number == source_inv.lot_number
                    and inv.expiry_date == source_inv.expiry_date
                    and inv.lpn == source_inv.lpn
                ),
                None,
            )

            dest_inv = ensure_inventory(
                self.db,
                dest_inv,
                tenant_id=self.tenant_id,
                client_id=source_inv.client_id,
                warehouse_id=source_inv.warehouse_id,
                location_id=allocation["location_id"],
                sku_id=task.sku_id,
                lot_number=source_inv.lot_number,
                expiry_date=source_inv.expiry_date,
                received_at=source_inv.received_at,
            )

            dest_loc = destination_locations[allocation["location_id"]]
            dest_loc.current_status = LocationStatus.OCCUPIED.value

            # Add to destination (and deduct the full task quantity from the
            # source alongside the first allocation), recording the transaction
            await post_movement(
                self.db,
                tenant_id=self.tenant_id,
                client_id=source_inv.client_id,
                transaction_type=TransactionType.PUTAWAY.value,
                sku_id=task.sku_id,
                location_id=allocation["location_id"],
                quantity_change=allocation["quantity"],
                inventory=dest_inv,
                delta_on_hand=allocation["quantity"],
                extra_deltas=(
                    [StockDelta(source_inv, on_hand=-task.quantity)]
                    if not source_deducted
                    else ()
                ),
                from_location_id=source_location_id,
                to_location_id=allocation["location_id"],
                reference_type=task.reference_type,
                reference_id=task.reference_id,
                performed_by=user_id,
                flush=False,
            )
            source_deducted = True

            self.db.add(
                PutawayAllocation(
                    tenant_id=self.tenant_id,
                    task_id=task.id,
                    location_id=allocation["location_id"],
                    quantity=allocation["quantity"],
                    sort_order=allocation["sort_order"],
                )
            )
            allocation_results.append(
                {
                    "location_id": allocation["location_id"],
                    "location_barcode": dest_loc.barcode,
                    "quantity": allocation["quantity"],
                }
            )

        if handling_unit:
            handling_unit.status = "stored"
            if handling_unit.inbound_package_id:
                package = await self.db.scalar(
                    select(InboundPackage).where(
                        InboundPackage.id == handling_unit.inbound_package_id,
                        InboundPackage.tenant_id == self.tenant_id,
                    )
                )
                if package:
                    package.status = InboundPackageStatus.STORED.value

        # Complete task
        task.status = TaskStatus.COMPLETED.value
        task.destination_location_id = normalized_allocations[0]["location_id"]
        task.assigned_to = user_id
        task.assigned_type = AssignedType.HUMAN.value
        task.completed_at = datetime.now(UTC)

        # Check if all putaway tasks for the inbound order are done
        if task.reference_type == "inbound_order":
            await self._check_inbound_complete(task.reference_id)

        await self.db.flush()
        return {
            "success": True,
            "task_id": task_id,
            "location": allocation_results[0]["location_barcode"],
            "quantity": task.quantity,
            "handling_unit_status": handling_unit.status if handling_unit else None,
            "allocations": allocation_results,
            "warnings": placement_warnings,
        }

    async def preview_putaway_confirmation(
        self,
        task_id: str,
        destination_location_id: str,
        allocations: list[dict] | None = None,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {
            "task_id": task_id,
            "destination_location_id": destination_location_id,
            "allocations": allocations,
        }
        endpoint = "POST /api/v1/fulfillment/putaway/confirm"
        entity = {"type": "putaway_task", "id": task_id, "task_id": task_id}
        state_before = await self._putaway_state(task_id)
        planned_result, state_after = await agent_preview.savepoint_dry_run(
            self.db,
            lambda: self.confirm_putaway(
                task_id=task_id,
                destination_location_id=destination_location_id,
                user_id=user_id or "agent-preview",
                allocations=allocations,
            ),
            lambda: self._putaway_state(task_id),
        )

        if not planned_result.get("success"):
            return agent_preview.blocked_preview(
                _PUTAWAY_CONFIRM,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="recover_or_choose_next_putaway_task",
                result={
                    "what_happened": planned_result.get("error") or "Putaway cannot be confirmed.",
                    "why_blocked": planned_result.get("error_code") or "putaway_preview_failed",
                    "recommended_action": "Review the task, destination, source stock, and recovery path.",
                    "safe_commands": [
                        "wms putaway next --dry-run --live-preview",
                        "wms putaway block --dry-run --task-id TASK --reason REASON",
                    ],
                },
            )

        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _PUTAWAY_CONFIRM,
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
            },
            records=[
                {
                    "type": "putaway_task",
                    "id": task_id,
                    "sku_id": state_before.get("sku_id"),
                    "quantity": state_before.get("quantity"),
                    "source_location_id": state_before.get("source_location_id"),
                    "destination_location_id": destination_location_id,
                }
            ],
            impact={
                "task_status": "completed",
                "inventory_move": planned_result.get("allocations", []),
                "warnings": planned_result.get("warnings", []),
            },
            result={
                "message": "No backend write was performed.",
                "planned_result": planned_result,
                "safe_commands": [
                    "wms putaway confirm --dry-run --live-preview",
                    "wms putaway next --dry-run --live-preview",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_putaway_with_token(
        self,
        task_id: str,
        destination_location_id: str,
        confirmation_token: str,
        user_id: str,
        allocations: list[dict] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _PUTAWAY_CONFIRM,
            confirmation_token,
            message="A putaway confirmation token is required before the agent can write.",
        )

        preview = await self.preview_putaway_confirmation(
            task_id=task_id,
            destination_location_id=destination_location_id,
            allocations=allocations,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _PUTAWAY_CONFIRM,
            preview,
            error_code="putaway_preview_failed",
            default_message="Putaway preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _PUTAWAY_CONFIRM,
            entity_id=task_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The putaway confirmation token no longer matches the current preview.",
        )

        result = await self.confirm_putaway(
            task_id=task_id,
            destination_location_id=destination_location_id,
            user_id=user_id,
            allocations=allocations,
        )
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _PUTAWAY_CONFIRM,
            evidence=evidence,
            ok=bool(result.get("success")),
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._putaway_state(task_id),
            payload_hash=payload_hash,
            next_action="choose_next_putaway_task_or_return_to_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=result.get("error") or result.get("error_code"),
        )

    async def _putaway_state(self, task_id: str) -> dict:
        task = await self.db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == self.tenant_id,
                Task.task_type == TaskType.PUTAWAY.value,
            )
        )
        if not task:
            return {"task_id": task_id, "task_status": "not_found"}
        return {
            "task_id": task.id,
            "task_status": task.status,
            "warehouse_id": task.warehouse_id,
            "sku_id": task.sku_id,
            "quantity": task.quantity,
            "source_location_id": task.source_location_id,
            "destination_location_id": task.destination_location_id,
            "handling_unit_id": task.handling_unit_id,
            "reference_type": task.reference_type,
            "reference_id": task.reference_id,
        }

    async def _check_inbound_complete(self, order_id: str) -> None:
        """If all putaway tasks are done, mark the inbound order as completed."""
        result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.tenant_id == self.tenant_id,
                Task.reference_type == "inbound_order",
                Task.reference_id == order_id,
                Task.status != TaskStatus.COMPLETED.value,
                Task.status != TaskStatus.CANCELLED.value,
            )
        )
        remaining = result.scalar()
        if remaining == 0:
            order_result = await self.db.execute(
                select(InboundOrder).where(
                    InboundOrder.id == order_id,
                    InboundOrder.tenant_id == self.tenant_id,
                )
            )
            order = order_result.scalar_one_or_none()
            if not order:
                return
            order.status = InboundStatus.COMPLETED.value
