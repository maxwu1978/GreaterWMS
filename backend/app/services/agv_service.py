"""
AGV Service — the bridge between WMS and AGV fleet management.

This service provides the API contract that AGV scheduling systems (WCS/RCS)
consume to get tasks, report status, and coordinate with human operators.

Integration pattern:
  WMS creates Tasks → AGV Scheduler polls /tasks?assigned_type=unassigned
  → Scheduler assigns task to AGV → AGV executes → Reports completion
  → WMS updates inventory via InventoryTransaction

The key design principle: Tasks are the universal unit of work. The same Task
model drives both human RF gun operators and AGV robots. The assigned_type
field determines who does the work.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory, TransactionType
from app.models.order import HandlingUnit, InboundOrderLine, ReceivingLabel
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.warehouse import Location, Warehouse
from app.services.inventory_ledger import post_movement
from app.services.putaway_execution_service import PutawayExecutionService


async def resolve_putaway_handling_unit(
    db: AsyncSession,
    tenant_id: str,
    task: Task,
) -> HandlingUnit | None:
    if task.task_type != TaskType.PUTAWAY.value or task.reference_type != "inbound_order":
        return None

    if task.handling_unit_id:
        return await db.scalar(
            select(HandlingUnit).where(
                HandlingUnit.tenant_id == tenant_id,
                HandlingUnit.id == task.handling_unit_id,
            )
        )

    exact_line = await db.scalar(
        select(InboundOrderLine).where(
            InboundOrderLine.tenant_id == tenant_id,
            InboundOrderLine.order_id == task.reference_id,
            InboundOrderLine.sku_id == task.sku_id,
            InboundOrderLine.staging_location_id == task.source_location_id,
        )
    )
    if exact_line:
        exact_match = await db.scalar(
            select(HandlingUnit).where(
                HandlingUnit.tenant_id == tenant_id,
                HandlingUnit.order_id == task.reference_id,
                HandlingUnit.order_line_id == exact_line.id,
            )
        )
        if exact_match:
            return exact_match
        exact_label = await db.scalar(
            select(ReceivingLabel).where(
                ReceivingLabel.tenant_id == tenant_id,
                ReceivingLabel.order_id == task.reference_id,
                ReceivingLabel.order_line_id == exact_line.id,
                ReceivingLabel.sku_id == task.sku_id,
            )
        )
        if exact_label:
            return await _create_handling_unit_from_label(
                db=db,
                tenant_id=tenant_id,
                task=task,
                line=exact_line,
                label=exact_label,
            )

    candidate_result = await db.execute(
        select(HandlingUnit).where(
            HandlingUnit.tenant_id == tenant_id,
            HandlingUnit.order_id == task.reference_id,
            HandlingUnit.sku_id == task.sku_id,
            HandlingUnit.status != "stored",
        )
    )
    candidates = candidate_result.scalars().all()
    if len(candidates) == 1:
        return candidates[0]

    label_result = await db.execute(
        select(ReceivingLabel, InboundOrderLine)
        .join(InboundOrderLine, InboundOrderLine.id == ReceivingLabel.order_line_id)
        .where(
            InboundOrderLine.tenant_id == tenant_id,
            ReceivingLabel.tenant_id == tenant_id,
            ReceivingLabel.order_id == task.reference_id,
            ReceivingLabel.sku_id == task.sku_id,
            ReceivingLabel.status.in_(["received", "pending"]),
            InboundOrderLine.quantity_received > 0,
        )
    )
    label_rows = label_result.all()
    if len(label_rows) == 1:
        label, line = label_rows[0]
        return await _create_handling_unit_from_label(
            db=db,
            tenant_id=tenant_id,
            task=task,
            line=line,
            label=label,
        )

    return None


async def _create_handling_unit_from_label(
    db: AsyncSession,
    tenant_id: str,
    task: Task,
    line: InboundOrderLine,
    label: ReceivingLabel,
) -> HandlingUnit:
    handling_unit = HandlingUnit(
        tenant_id=tenant_id,
        order_id=task.reference_id or line.order_id,
        order_line_id=line.id,
        receiving_label_id=label.id,
        sku_id=line.sku_id,
        unit_code=label.label_code,
        unit_type=label.label_type or "carton",
        expected_qty=label.expected_qty or line.quantity_expected,
        received_qty=label.received_qty
        or max(0, (line.quantity_received or 0) - (line.quantity_damaged or 0)),
        damaged_qty=line.quantity_damaged or 0,
        status="putaway_pending",
        staging_location_id=line.staging_location_id,
        lot_number=label.lot_number or line.lot_number,
        expiry_date=label.expiry_date or line.expiry_date,
        external_tracking_number=label.external_tracking_number,
        external_carton_mark=label.external_carton_mark,
        external_customer_barcode=label.external_customer_barcode,
        measured_weight_kg=line.measured_weight_kg,
        measured_length_cm=line.measured_length_cm,
        measured_width_cm=line.measured_width_cm,
        measured_height_cm=line.measured_height_cm,
        package_count=line.package_count,
        pallet_count=line.pallet_count,
        rent_free_days=line.rent_free_days,
        note=line.receiving_note,
    )
    db.add(handling_unit)
    await db.flush()
    return handling_unit


class AGVService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def _get_warehouse(self, warehouse_id: str) -> Warehouse | None:
        result = await self.db.execute(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == self.tenant_id,
                Warehouse.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_tasks(
        self,
        warehouse_id: str,
        task_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get pending unassigned tasks for AGV scheduler to claim.
        Returns tasks with full location coordinates for path planning.
        """
        warehouse = await self._get_warehouse(warehouse_id)
        if not warehouse:
            return []

        query = (
            select(Task, Location)
            .outerjoin(
                Location,
                (Location.id == Task.source_location_id)
                & (Location.tenant_id == self.tenant_id),
            )
            .where(
                Task.tenant_id == self.tenant_id,
                Task.warehouse_id == warehouse_id,
                Task.status == TaskStatus.PENDING.value,
                Task.assigned_type == AssignedType.UNASSIGNED.value,
            )
        )

        if task_types:
            query = query.where(Task.task_type.in_(task_types))

        query = query.order_by(Task.priority, Task.created_at).limit(limit)
        result = await self.db.execute(query)
        rows = result.all()

        for task, _ in rows:
            if (
                task.task_type != TaskType.PUTAWAY.value
                or task.handling_unit_id
                or task.reference_type != "inbound_order"
            ):
                continue
            handling_unit = await resolve_putaway_handling_unit(
                self.db,
                self.tenant_id,
                task,
            )
            if handling_unit:
                task.handling_unit_id = handling_unit.id

        await self.db.flush()

        handling_unit_ids = {task.handling_unit_id for task, _ in rows if task.handling_unit_id}
        handling_unit_map: dict[str, HandlingUnit] = {}
        if handling_unit_ids:
            handling_unit_result = await self.db.execute(
                select(HandlingUnit).where(
                    HandlingUnit.tenant_id == self.tenant_id,
                    HandlingUnit.id.in_(handling_unit_ids),
                )
            )
            handling_unit_map = {
                handling_unit.id: handling_unit for handling_unit in handling_unit_result.scalars()
            }

        # Batch-fetch destination location coordinates
        destination_location_ids = {
            task.destination_location_id for task, _ in rows if task.destination_location_id
        }
        dest_loc_map: dict[str, Location] = {}
        if destination_location_ids:
            dest_result = await self.db.execute(
                select(Location).where(
                    Location.tenant_id == self.tenant_id,
                    Location.id.in_(destination_location_ids),
                )
            )
            dest_loc_map = {location.id: location for location in dest_result.scalars()}

        tasks = []
        execution_service = PutawayExecutionService(self.db, self.tenant_id)
        for task, source_loc in rows:
            dest_loc = (
                dest_loc_map.get(task.destination_location_id)
                if task.destination_location_id
                else None
            )
            handling_unit = (
                handling_unit_map.get(task.handling_unit_id) if task.handling_unit_id else None
            )
            execution = await execution_service.decide(
                warehouse_id=task.warehouse_id,
                source_location_id=task.source_location_id,
                handling_unit_id=task.handling_unit_id,
            )

            tasks.append(
                {
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "priority": task.priority,
                    "sku_id": task.sku_id,
                    "quantity": task.quantity,
                    "lpn": task.lpn,
                    "handling_unit_id": task.handling_unit_id,
                    "handling_unit_code": handling_unit.unit_code if handling_unit else None,
                    "handling_unit_status": handling_unit.status if handling_unit else None,
                    "package_count": handling_unit.package_count if handling_unit else None,
                    "pallet_count": handling_unit.pallet_count if handling_unit else None,
                    "rent_free_days": handling_unit.rent_free_days if handling_unit else None,
                    "measured_weight_kg": float(handling_unit.measured_weight_kg)
                    if handling_unit and handling_unit.measured_weight_kg is not None
                    else None,
                    "external_tracking_number": handling_unit.external_tracking_number
                    if handling_unit
                    else None,
                    "external_carton_mark": handling_unit.external_carton_mark
                    if handling_unit
                    else None,
                    "external_customer_barcode": handling_unit.external_customer_barcode
                    if handling_unit
                    else None,
                    "execution_mode": task.execution_mode or execution.mode,
                    "agv_eligible": execution.agv_eligible,
                    "execution_reason": execution.reason,
                    "handling_unit": {
                        "unit_code": handling_unit.unit_code,
                        "unit_type": handling_unit.unit_type,
                        "status": handling_unit.status,
                        "external_tracking_number": handling_unit.external_tracking_number,
                        "external_carton_mark": handling_unit.external_carton_mark,
                        "external_customer_barcode": handling_unit.external_customer_barcode,
                        "measured_weight_kg": float(handling_unit.measured_weight_kg)
                        if handling_unit.measured_weight_kg is not None
                        else None,
                        "package_count": handling_unit.package_count,
                        "pallet_count": handling_unit.pallet_count,
                        "rent_free_days": handling_unit.rent_free_days,
                    }
                    if handling_unit
                    else None,
                    "source_barcode": source_loc.barcode if source_loc else None,
                    "destination_barcode": dest_loc.barcode if dest_loc else None,
                    "source": {
                        "location_id": task.source_location_id,
                        "barcode": source_loc.barcode if source_loc else None,
                        "coordinate_x": float(source_loc.coordinate_x)
                        if source_loc and source_loc.coordinate_x
                        else None,
                        "coordinate_y": float(source_loc.coordinate_y)
                        if source_loc and source_loc.coordinate_y
                        else None,
                        "coordinate_z": float(source_loc.coordinate_z)
                        if source_loc and source_loc.coordinate_z
                        else None,
                    }
                    if source_loc
                    else None,
                    "destination": {
                        "location_id": task.destination_location_id,
                        "barcode": dest_loc.barcode if dest_loc else None,
                        "coordinate_x": float(dest_loc.coordinate_x)
                        if dest_loc and dest_loc.coordinate_x
                        else None,
                        "coordinate_y": float(dest_loc.coordinate_y)
                        if dest_loc and dest_loc.coordinate_y
                        else None,
                        "coordinate_z": float(dest_loc.coordinate_z)
                        if dest_loc and dest_loc.coordinate_z
                        else None,
                    }
                    if dest_loc
                    else None,
                    "reference_type": task.reference_type,
                    "reference_id": task.reference_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                }
            )

        return tasks

    async def assign_task(
        self,
        task_id: str,
        agv_unit_id: str,
    ) -> dict:
        """
        AGV scheduler claims a task for a specific AGV unit.
        Sets assigned_type to 'agv' and records the unit ID.
        """
        result = await self.db.execute(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        task = result.scalar_one()

        if task.status != TaskStatus.PENDING.value:
            return {"success": False, "error": f"Task is {task.status}, not pending"}

        task.assigned_type = AssignedType.AGV.value
        task.assigned_to = f"agv:{agv_unit_id}"
        task.status = TaskStatus.ASSIGNED.value
        task.assigned_at = datetime.now(UTC)

        await self.db.flush()
        return {"success": True, "task_id": task_id, "assigned_to": task.assigned_to}

    async def start_task(self, task_id: str, agv_unit_id: str) -> dict:
        """AGV reports it has started executing the task (en route)."""
        result = await self.db.execute(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        task = result.scalar_one()

        if task.assigned_to != f"agv:{agv_unit_id}":
            return {"success": False, "error": "Task not assigned to this AGV"}

        task.status = TaskStatus.IN_PROGRESS.value
        task.started_at = datetime.now(UTC)

        await self.db.flush()
        return {"success": True, "task_id": task_id, "status": "in_progress"}

    async def complete_task(
        self,
        task_id: str,
        agv_unit_id: str,
        actual_quantity: int | None = None,
    ) -> dict:
        """
        AGV reports task completion.
        Triggers inventory update via InventoryTransaction.
        """
        result = await self.db.execute(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        task = result.scalar_one()

        if task.assigned_to != f"agv:{agv_unit_id}":
            return {"success": False, "error": "Task not assigned to this AGV"}

        quantity = actual_quantity or task.quantity
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.now(UTC)

        # Record inventory transaction based on task type
        if task.task_type in (TaskType.PICK.value, TaskType.MOVE.value, TaskType.PUTAWAY.value):
            # Determine client_id from inventory at source
            client_id = ""
            if task.source_location_id and task.sku_id:
                inv_result = await self.db.execute(
                    select(Inventory.client_id)
                    .where(
                        Inventory.tenant_id == self.tenant_id,
                        Inventory.location_id == task.source_location_id,
                        Inventory.sku_id == task.sku_id,
                    )
                    .limit(1)
                )
                client_row = inv_result.first()
                if client_row:
                    client_id = client_row[0]

            txn_type = {
                TaskType.PICK.value: TransactionType.PICK.value,
                TaskType.MOVE.value: TransactionType.MOVE.value,
                TaskType.PUTAWAY.value: TransactionType.PUTAWAY.value,
            }.get(task.task_type, TransactionType.MOVE.value)

            # Ledger-only: AGV completion reports do not adjust stock directly
            await post_movement(
                self.db,
                tenant_id=self.tenant_id,
                client_id=client_id,
                transaction_type=txn_type,
                sku_id=task.sku_id or "",
                location_id=task.destination_location_id or task.source_location_id or "",
                quantity_change=-quantity if task.task_type == TaskType.PICK.value else quantity,
                from_location_id=task.source_location_id,
                to_location_id=task.destination_location_id,
                reference_type=task.reference_type,
                reference_id=task.reference_id,
                performed_by=task.assigned_to,
                notes=f"Completed by AGV unit {agv_unit_id}",
                flush=False,
            )

        await self.db.flush()
        return {
            "success": True,
            "task_id": task_id,
            "status": "completed",
            "quantity": quantity,
        }

    async def fail_task(
        self,
        task_id: str,
        agv_unit_id: str,
        reason: str,
    ) -> dict:
        """AGV reports task failure (obstacle, hardware error, etc.)."""
        result = await self.db.execute(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        task = result.scalar_one()

        task.status = TaskStatus.FAILED.value
        task.failure_reason = reason
        task.retry_count += 1

        await self.db.flush()
        return {
            "success": True,
            "task_id": task_id,
            "status": "failed",
            "retry_count": task.retry_count,
            "can_retry": task.retry_count < 3,
        }

    async def get_agv_accessible_locations(self, warehouse_id: str) -> list[dict]:
        """Return all AGV-accessible locations with coordinates for map building."""
        warehouse = await self._get_warehouse(warehouse_id)
        if not warehouse:
            return []

        result = await self.db.execute(
            select(Location)
            .where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
                Location.is_agv_accessible == True,  # noqa: E712
                Location.coordinate_x.is_not(None),
                Location.coordinate_y.is_not(None),
            )
            .order_by(Location.pick_sequence)
        )

        return [
            {
                "location_id": loc.id,
                "barcode": loc.barcode,
                "type": loc.location_type,
                "status": loc.current_status,
                "coordinate": {
                    "x": float(loc.coordinate_x) if loc.coordinate_x else 0,
                    "y": float(loc.coordinate_y) if loc.coordinate_y else 0,
                    "z": float(loc.coordinate_z) if loc.coordinate_z else 0,
                },
            }
            for loc in result.scalars()
        ]

    async def validate_coordinates(self, warehouse_id: str) -> dict:
        """
        Validate that all AGV-accessible locations have valid coordinates.
        Run this before AGV deployment to catch missing data.
        """
        warehouse = await self._get_warehouse(warehouse_id)
        if not warehouse:
            return {
                "warehouse_id": warehouse_id,
                "warehouse_found": False,
                "total_agv_locations": 0,
                "valid": 0,
                "issues": [{"issue": "warehouse_not_found"}],
                "planner_profile": None,
                "ready": False,
            }

        planner_profile = (warehouse.address or {}).get("_planner_rules") or {}
        aisle_width_m = float(planner_profile.get("aisle_width_m", 3.2))
        turning_radius_m = float(planner_profile.get("agv_turning_radius_m", 1.8))
        rack_height_m = float(planner_profile.get("rack_height_m", 7.5))
        beam_capacity_kg = float(planner_profile.get("beam_capacity_kg", 1200.0))

        result = await self.db.execute(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
                Location.is_agv_accessible == True,  # noqa: E712
            )
        )
        locations = result.scalars().all()

        issues = []
        for loc in locations:
            if loc.coordinate_x is None or loc.coordinate_y is None:
                issues.append(
                    {
                        "location_id": loc.id,
                        "barcode": loc.barcode,
                        "issue": "missing_coordinates",
                    }
                )

        if aisle_width_m < 2.8:
            issues.append(
                {
                    "issue": "aisle_width_below_agv_threshold",
                    "threshold_m": 2.8,
                    "actual_m": aisle_width_m,
                }
            )

        if turning_radius_m < 1.4:
            issues.append(
                {
                    "issue": "turning_radius_below_agv_threshold",
                    "threshold_m": 1.4,
                    "actual_m": turning_radius_m,
                }
            )

        return {
            "warehouse_id": warehouse_id,
            "warehouse_found": True,
            "total_agv_locations": len(locations),
            "valid": len(locations) - len(issues),
            "issues": issues,
            "planner_profile": {
                "aisle_width_m": aisle_width_m,
                "agv_turning_radius_m": turning_radius_m,
                "rack_height_m": rack_height_m,
                "beam_capacity_kg": beam_capacity_kg,
            },
            "ready": len(locations) > 0 and len(issues) == 0,
        }
