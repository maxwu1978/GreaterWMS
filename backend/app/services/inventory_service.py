"""
Inventory Service — inventory moves, adjustments, and cycle counts.

These operations maintain inventory accuracy between receiving and shipping.
"""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import for_update
from app.models.inventory import Inventory, TransactionType
from app.models.warehouse import Location, LocationStatus
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import StockDelta, ensure_inventory, post_movement
from app.services.outbound_readiness import (
    refresh_pending_outbound_readiness_for_inventory_change,
)

_INVENTORY_ADJUST = AgentGateSpec(
    action="inventory.adjust",
    risk="medium",
    permission="master_data.manage",
    entity_type="inventory",
    token_prefix="inv-adjust",
)


class InventoryService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def move_inventory(
        self,
        inventory_id: str,
        to_location_id: str,
        quantity: int,
        user_id: str,
        reason: str | None = None,
    ) -> dict:
        """
        Move inventory from one location to another.
        Used for replenishment, consolidation, or reorganization.
        """
        result = await self.db.execute(
            for_update(select(Inventory).where(Inventory.id == inventory_id))
        )
        source = result.scalar_one()

        if source.quantity_on_hand - source.quantity_allocated < quantity:
            return {"success": False, "error": "Insufficient available quantity"}

        # Find (or create) the destination row
        dest_result = await self.db.execute(
            select(Inventory).where(
                Inventory.tenant_id == self.tenant_id,
                Inventory.location_id == to_location_id,
                Inventory.sku_id == source.sku_id,
                Inventory.lot_number == source.lot_number,
            )
        )
        dest = ensure_inventory(
            self.db,
            dest_result.scalar_one_or_none(),
            tenant_id=self.tenant_id,
            client_id=source.client_id,
            warehouse_id=source.warehouse_id,
            location_id=to_location_id,
            sku_id=source.sku_id,
            lot_number=source.lot_number,
            expiry_date=source.expiry_date,
            received_at=source.received_at,
        )

        # Deduct from source, add to destination, record the transaction
        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=source.client_id,
            transaction_type=TransactionType.MOVE.value,
            sku_id=source.sku_id,
            location_id=to_location_id,
            quantity_change=quantity,
            inventory=dest,
            delta_on_hand=quantity,
            extra_deltas=[StockDelta(source, on_hand=-quantity)],
            from_location_id=source.location_id,
            to_location_id=to_location_id,
            performed_by=user_id,
            notes=reason,
            flush=False,
        )

        # Update location statuses
        if source.quantity_on_hand <= 0:
            loc_result = await self.db.execute(
                select(Location).where(Location.id == source.location_id)
            )
            loc = loc_result.scalar_one()
            loc.current_status = LocationStatus.AVAILABLE.value

        await self.db.flush()
        return {"success": True, "moved": quantity, "to_location": to_location_id}

    async def adjust_inventory(
        self,
        inventory_id: str,
        new_quantity: int,
        user_id: str,
        reason: str,
    ) -> dict:
        """
        Manual inventory adjustment — used when physical count differs from system.
        Creates an audit trail via InventoryTransaction.
        """
        if not reason.strip():
            return {"success": False, "error": "Adjustment reason is required"}

        result = await self.db.execute(
            for_update(
                select(Inventory).where(
                    Inventory.id == inventory_id,
                    Inventory.tenant_id == self.tenant_id,
                )
            )
        )
        inv = result.scalar_one()

        old_qty = inv.quantity_on_hand
        adjustment = new_quantity - old_qty

        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=inv.client_id,
            transaction_type=TransactionType.ADJUST.value,
            sku_id=inv.sku_id,
            location_id=inv.location_id,
            quantity_change=adjustment,
            inventory=inv,
            delta_on_hand=adjustment,
            performed_by=user_id,
            notes=f"Adjustment: {old_qty} → {new_quantity}. Reason: {reason}",
        )
        readiness_stats = await refresh_pending_outbound_readiness_for_inventory_change(
            self.db,
            self.tenant_id,
            warehouse_id=inv.warehouse_id,
            sku_ids=[inv.sku_id],
        )
        return {
            "success": True,
            "previous": old_qty,
            "new": new_quantity,
            "adjustment": adjustment,
            "readiness_refresh": {
                "scanned_orders": readiness_stats.scanned_orders,
                "updated_orders": readiness_stats.updated_orders,
                "unchanged_orders": readiness_stats.unchanged_orders,
            },
        }

    async def preview_adjust_inventory(
        self,
        inventory_id: str,
        new_quantity: int,
        reason: str,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"inventory_id": inventory_id, "new_quantity": new_quantity, "reason": reason}
        endpoint = "POST /api/v1/inventory/ops/adjust"
        entity = {"type": "inventory", "id": inventory_id, "inventory_id": inventory_id}
        state_before = await self._inventory_state(inventory_id)
        if state_before.get("inventory_status") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")
        if not reason.strip():
            return agent_preview.blocked_preview(
                _INVENTORY_ADJUST,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="provide_adjustment_reason",
                result={
                    "what_happened": "Inventory adjustment needs a reason.",
                    "why_blocked": "inventory_adjust_reason_required",
                    "recommended_action": "Add a cycle-count or audit reason before previewing again.",
                    "safe_commands": ["wms inventory adjust --dry-run --reason REASON"],
                },
            )

        # No savepoint dry run here: the adjustment's projected state is a pure
        # arithmetic delta, so the preview computes state_after directly.
        old_qty = int(state_before.get("quantity_on_hand") or 0)
        adjustment = new_quantity - old_qty
        state_after = {
            **state_before,
            "quantity_on_hand": new_quantity,
            "adjustment": adjustment,
        }
        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _INVENTORY_ADJUST,
            entity=entity,
            entity_id=inventory_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"inventory_id": inventory_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "inventory_id": inventory_id,
            },
            records=[
                {
                    "type": "inventory",
                    "id": inventory_id,
                    "sku_id": state_before.get("sku_id"),
                    "location_id": state_before.get("location_id"),
                    "previous_quantity": old_qty,
                    "new_quantity": new_quantity,
                    "adjustment": adjustment,
                }
            ],
            impact={"transaction_type": "adjust", "reason": reason},
            result={
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms inventory adjust --dry-run --live-preview",
                    "wms inventory lookup --query SKU",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_adjust_inventory_with_token(
        self,
        inventory_id: str,
        new_quantity: int,
        reason: str,
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _INVENTORY_ADJUST,
            confirmation_token,
            message="An inventory adjustment token is required before the agent can write.",
        )

        preview = await self.preview_adjust_inventory(
            inventory_id=inventory_id,
            new_quantity=new_quantity,
            reason=reason,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _INVENTORY_ADJUST,
            preview,
            error_code="inventory_adjust_preview_failed",
            default_message="Inventory adjustment preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _INVENTORY_ADJUST,
            entity_id=inventory_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The inventory adjustment token no longer matches the current preview.",
        )

        result = await self.adjust_inventory(
            inventory_id=inventory_id,
            new_quantity=new_quantity,
            user_id=user_id,
            reason=reason,
        )
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _INVENTORY_ADJUST,
            evidence=evidence,
            ok=bool(result.get("success")),
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._inventory_state(inventory_id),
            payload_hash=payload_hash,
            next_action="review_inventory_or_return_to_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=result.get("error"),
        )

    async def _inventory_state(self, inventory_id: str) -> dict:
        inv = await self.db.scalar(
            select(Inventory).where(
                Inventory.id == inventory_id,
                Inventory.tenant_id == self.tenant_id,
            )
        )
        if not inv:
            return {"inventory_id": inventory_id, "inventory_status": "not_found"}
        return {
            "inventory_id": inv.id,
            "warehouse_id": inv.warehouse_id,
            "client_id": inv.client_id,
            "sku_id": inv.sku_id,
            "location_id": inv.location_id,
            "quantity_on_hand": inv.quantity_on_hand,
            "quantity_allocated": inv.quantity_allocated,
            "quantity_damaged": inv.quantity_damaged,
            "lot_number": inv.lot_number,
            "expiry_date": inv.expiry_date.isoformat() if inv.expiry_date else None,
        }

    async def update_inventory_lot(
        self,
        inventory_id: str,
        lot_number: str,
        user_id: str,
        expiry_date: datetime | None = None,
        reason: str | None = None,
    ) -> dict:
        """
        Backfill or correct lot metadata for an existing inventory row.
        Keeps quantity unchanged but appends an audit transaction.
        """
        result = await self.db.execute(
            for_update(
                select(Inventory).where(
                    Inventory.id == inventory_id,
                    Inventory.tenant_id == self.tenant_id,
                )
            )
        )
        inv = result.scalar_one()
        old_lot = inv.lot_number
        old_expiry = inv.expiry_date
        inv.lot_number = lot_number.strip() or None
        if expiry_date is not None:
            inv.expiry_date = expiry_date

        note_parts = [
            f"Lot update: {old_lot or 'missing'} → {inv.lot_number or 'missing'}",
        ]
        if expiry_date is not None:
            note_parts.append(
                f"Expiry: {(old_expiry.isoformat() if old_expiry else 'missing')} → {expiry_date.isoformat()}"
            )
        if reason:
            note_parts.append(f"Reason: {reason}")

        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=inv.client_id,
            transaction_type=TransactionType.ADJUST.value,
            sku_id=inv.sku_id,
            location_id=inv.location_id,
            quantity_change=0,
            inventory=inv,
            performed_by=user_id,
            lot_number=inv.lot_number,
            notes=". ".join(note_parts),
        )
        return {
            "success": True,
            "inventory_id": inv.id,
            "lot_number": inv.lot_number,
            "expiry_date": inv.expiry_date.isoformat() if inv.expiry_date else None,
        }

    async def cycle_count(
        self,
        location_id: str,
        counts: list[dict],
        user_id: str,
    ) -> list[dict]:
        """
        Cycle count at a location — operator scans location then counts each SKU.

        counts: [{"sku_id": "...", "counted_quantity": 10}, ...]

        Returns discrepancy report for each SKU.
        """
        results = []
        changed_skus_by_warehouse: dict[str, set[str]] = {}

        for count in counts:
            sku_id = count["sku_id"]
            counted = count["counted_quantity"]

            inv_result = await self.db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == location_id,
                    Inventory.sku_id == sku_id,
                )
            )
            inv = inv_result.scalar_one_or_none()

            system_qty = inv.quantity_on_hand if inv else 0
            discrepancy = counted - system_qty

            if discrepancy != 0:
                if inv:
                    changed_skus_by_warehouse.setdefault(inv.warehouse_id, set()).add(sku_id)
                elif counted > 0:
                    # Found items not in system — need client_id lookup
                    # For now, skip creating new inventory without client context
                    results.append(
                        {
                            "sku_id": sku_id,
                            "system": 0,
                            "counted": counted,
                            "discrepancy": counted,
                            "status": "unregistered_sku_at_location",
                        }
                    )
                    continue

                await post_movement(
                    self.db,
                    tenant_id=self.tenant_id,
                    client_id=inv.client_id if inv else "",
                    transaction_type=TransactionType.CYCLE_COUNT.value,
                    sku_id=sku_id,
                    location_id=location_id,
                    quantity_change=discrepancy,
                    inventory=inv,
                    delta_on_hand=discrepancy if inv else 0,
                    performed_by=user_id,
                    notes=f"Cycle count: system={system_qty} counted={counted} variance={discrepancy}",
                    flush=False,
                )

            results.append(
                {
                    "sku_id": sku_id,
                    "system": system_qty,
                    "counted": counted,
                    "discrepancy": discrepancy,
                    "status": "match" if discrepancy == 0 else "variance",
                }
            )

        await self.db.flush()
        for warehouse_id, sku_ids in changed_skus_by_warehouse.items():
            await refresh_pending_outbound_readiness_for_inventory_change(
                self.db,
                self.tenant_id,
                warehouse_id=warehouse_id,
                sku_ids=sku_ids,
            )
        return results
