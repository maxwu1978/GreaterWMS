"""
Cycle Count Service — generate count tasks, record counts, produce variance report.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import SKU, Inventory, InventoryTransaction, TransactionType
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.warehouse import Location
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import StockDelta, ensure_inventory, post_movement

_INVENTORY_COUNT = AgentGateSpec(
    action="inventory.count",
    risk="medium",
    permission="master_data.manage",
    entity_type="inventory_count",
    token_prefix="inv-count",
)


class CycleCountService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def generate_count_tasks(
        self,
        warehouse_id: str,
        zone_id: str | None = None,
        location_ids: list[str] | None = None,
    ) -> dict:
        """Generate cycle count tasks for specified locations or entire zone/warehouse."""
        query = select(Location).where(
            Location.tenant_id == self.tenant_id,
            Location.warehouse_id == warehouse_id,
            Location.current_status != "blocked",
        )
        if zone_id:
            query = query.where(Location.zone_id == zone_id)
        if location_ids:
            query = query.where(Location.id.in_(location_ids))

        result = await self.db.execute(query.order_by(Location.pick_sequence))
        locations = list(result.scalars())

        tasks_created = 0
        for loc in locations:
            existing_task = await self.db.scalar(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.warehouse_id == warehouse_id,
                    Task.task_type == TaskType.CYCLE_COUNT.value,
                    Task.source_location_id == loc.id,
                    Task.status.in_([TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value]),
                )
            )
            if existing_task:
                continue

            # Check if location has inventory
            inv_count = (
                await self.db.execute(
                    select(func.count(Inventory.id)).where(
                        Inventory.tenant_id == self.tenant_id,
                        Inventory.location_id == loc.id,
                        Inventory.quantity_on_hand > 0,
                    )
                )
            ).scalar() or 0

            if inv_count > 0 or not location_ids:  # Count even empty if explicitly requested
                task = Task(
                    tenant_id=self.tenant_id,
                    warehouse_id=warehouse_id,
                    task_type=TaskType.CYCLE_COUNT.value,
                    status=TaskStatus.PENDING.value,
                    priority=7,
                    source_location_id=loc.id,
                    reference_type="cycle_count",
                    reference_id=f"CC-{datetime.now(UTC).strftime('%Y%m%d')}",
                    assigned_type=AssignedType.UNASSIGNED.value,
                )
                self.db.add(task)
                tasks_created += 1

        await self.db.flush()
        return {
            "tasks_created": tasks_created,
            "locations_scanned": len(locations),
            "reference": f"CC-{datetime.now(UTC).strftime('%Y%m%d')}",
        }

    async def record_count(
        self,
        location_id: str,
        counts: list[dict],
        user_id: str,
    ) -> list[dict]:
        """
        Record actual counted quantities at a location.
        counts: [{"sku_id": "...", "counted_quantity": N}, ...]
        Returns variance report for this location.
        """
        counted_sku_ids = {count["sku_id"] for count in counts}

        inventory_by_sku: dict[str, list[Inventory]] = {}
        sku_rows_by_id: dict[str, object] = {}
        if counted_sku_ids:
            inv_result = await self.db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == location_id,
                    Inventory.sku_id.in_(counted_sku_ids),
                )
            )
            for row in inv_result.scalars():
                inventory_by_sku.setdefault(row.sku_id, []).append(row)

            sku_result = await self.db.execute(
                select(SKU.id, SKU.sku_code, SKU.client_id).where(
                    SKU.tenant_id == self.tenant_id, SKU.id.in_(counted_sku_ids)
                )
            )
            sku_rows_by_id = {row.id: row for row in sku_result.all()}

        location_result = await self.db.execute(
            select(Location.warehouse_id).where(
                Location.tenant_id == self.tenant_id, Location.id == location_id
            )
        )
        location_warehouse_id = location_result.scalar_one_or_none()

        results = []
        for count in counts:
            sku_id = count["sku_id"]
            counted = count["counted_quantity"]

            inventory_rows = inventory_by_sku.get(sku_id, [])
            primary_inventory = inventory_rows[0] if inventory_rows else None
            system_qty = sum(row.quantity_on_hand for row in inventory_rows)
            variance = counted - system_qty

            sku_row = sku_rows_by_id.get(sku_id)
            sku_code = (sku_row.sku_code if sku_row else None) or sku_id

            if variance != 0:
                deltas: list[StockDelta] = []
                if inventory_rows:
                    if variance > 0 and primary_inventory:
                        deltas.append(StockDelta(primary_inventory, on_hand=variance))
                    elif variance < 0:
                        remaining_to_remove = abs(variance)
                        for row in inventory_rows:
                            if remaining_to_remove <= 0:
                                break
                            removable = min(row.quantity_on_hand, remaining_to_remove)
                            deltas.append(StockDelta(row, on_hand=-removable))
                            remaining_to_remove -= removable
                elif counted > 0 and sku_row:
                    warehouse_id = location_warehouse_id
                    if warehouse_id:
                        primary_inventory = ensure_inventory(
                            self.db,
                            None,
                            tenant_id=self.tenant_id,
                            client_id=sku_row.client_id,
                            warehouse_id=warehouse_id,
                            location_id=location_id,
                            sku_id=sku_id,
                        )
                        deltas.append(StockDelta(primary_inventory, on_hand=counted))

                await post_movement(
                    self.db,
                    tenant_id=self.tenant_id,
                    client_id=(
                        primary_inventory.client_id
                        if primary_inventory
                        else (sku_row.client_id if sku_row else "")
                    ),
                    transaction_type=TransactionType.CYCLE_COUNT.value,
                    sku_id=sku_id,
                    location_id=location_id,
                    quantity_change=variance,
                    extra_deltas=deltas,
                    performed_by=user_id,
                    notes=f"Cycle count: system={system_qty} counted={counted} variance={variance}",
                    flush=False,
                )

            results.append(
                {
                    "sku_id": sku_id,
                    "sku_code": sku_code,
                    "system_qty": system_qty,
                    "counted_qty": counted,
                    "variance": variance,
                    "status": "match" if variance == 0 else ("over" if variance > 0 else "short"),
                }
            )

        # Complete cycle count task for this location
        task_result = await self.db.execute(
            select(Task).where(
                Task.tenant_id == self.tenant_id,
                Task.source_location_id == location_id,
                Task.task_type == TaskType.CYCLE_COUNT.value,
                Task.status.in_([TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value]),
            )
        )
        tasks = list(task_result.scalars())
        for task in tasks:
            task.status = TaskStatus.COMPLETED.value
            task.assigned_to = user_id
            task.completed_at = datetime.now(UTC)

        await self.db.flush()
        return results

    async def preview_record_count(
        self,
        location_id: str,
        counts: list[dict],
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"location_id": location_id, "counts": counts}
        endpoint = "POST /api/v1/cycle-count/record"
        state_before = await self._count_state(location_id, counts)
        planned_result, state_after = await agent_preview.savepoint_dry_run(
            self.db,
            lambda: self.record_count(
                location_id=location_id,
                counts=counts,
                user_id=user_id or "agent-preview",
            ),
            lambda: self._count_state(location_id, counts),
        )

        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _INVENTORY_COUNT,
            entity={"type": "inventory_count", "id": location_id, "location_id": location_id},
            entity_id=location_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"location_id": location_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "location_id": location_id,
            },
            records=[
                {
                    "type": "cycle_count",
                    "id": location_id,
                    "location_id": location_id,
                    "counts": counts,
                }
            ],
            impact={"variances": planned_result},
            result={
                "message": "No backend write was performed.",
                "planned_result": planned_result,
                "safe_commands": [
                    "wms inventory count --dry-run --live-preview",
                    "wms inventory lookup --query SKU",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_record_count_with_token(
        self,
        location_id: str,
        counts: list[dict],
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _INVENTORY_COUNT,
            confirmation_token,
            message="An inventory count token is required before the agent can write.",
        )

        preview = await self.preview_record_count(
            location_id=location_id,
            counts=counts,
            user_id=user_id,
            persist_evidence=False,
        )
        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _INVENTORY_COUNT,
            entity_id=location_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The inventory count token no longer matches the current preview.",
        )

        result = await self.record_count(location_id=location_id, counts=counts, user_id=user_id)
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _INVENTORY_COUNT,
            evidence=evidence,
            ok=True,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._count_state(location_id, counts),
            payload_hash=payload_hash,
            next_action="review_variances_or_return_to_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

    async def _count_state(self, location_id: str, counts: list[dict]) -> dict:
        sku_ids = [count["sku_id"] for count in counts]
        location = await self.db.scalar(
            select(Location).where(Location.id == location_id, Location.tenant_id == self.tenant_id)
        )
        rows = (
            await self.db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == location_id,
                    Inventory.sku_id.in_(sku_ids),
                )
            )
        ).scalars().all()
        return {
            "location_id": location_id,
            "warehouse_id": location.warehouse_id if location else None,
            "inventory": [
                {
                    "id": row.id,
                    "sku_id": row.sku_id,
                    "quantity_on_hand": row.quantity_on_hand,
                    "quantity_allocated": row.quantity_allocated,
                    "quantity_damaged": row.quantity_damaged,
                }
                for row in rows
            ],
            "counts": counts,
        }

    async def get_variance_report(self, reference_id: str | None = None) -> dict:
        """Get variance summary from cycle count transactions."""
        query = select(InventoryTransaction).where(
            InventoryTransaction.tenant_id == self.tenant_id,
            InventoryTransaction.transaction_type == TransactionType.CYCLE_COUNT.value,
        )
        if reference_id:
            query = query.where(InventoryTransaction.reference_id == reference_id)

        result = await self.db.execute(
            query.order_by(InventoryTransaction.performed_at.desc()).limit(200)
        )
        txns = list(result.scalars())

        variances = []
        total_over = 0
        total_short = 0
        for t in txns:
            sku_result = await self.db.execute(
                select(SKU.sku_code).where(SKU.tenant_id == self.tenant_id, SKU.id == t.sku_id)
            )
            sku_code = sku_result.scalar() or t.sku_id
            loc_result = await self.db.execute(
                select(Location.barcode).where(
                    Location.tenant_id == self.tenant_id, Location.id == t.location_id
                )
            )
            loc_barcode = loc_result.scalar() or t.location_id

            if t.quantity_change > 0:
                total_over += t.quantity_change
            else:
                total_short += abs(t.quantity_change)

            variances.append(
                {
                    "sku_code": sku_code,
                    "location": loc_barcode,
                    "variance": t.quantity_change,
                    "type": "over" if t.quantity_change > 0 else "short",
                    "counted_by": t.performed_by,
                    "date": t.performed_at.isoformat() if t.performed_at else "",
                    "notes": t.notes,
                }
            )

        return {
            "total_adjustments": len(variances),
            "total_over": total_over,
            "total_short": total_short,
            "net_variance": total_over - total_short,
            "variances": variances,
        }
