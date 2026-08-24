"""
Inventory Rules Service — safety stock, reorder alerts, putaway rules,
inventory freeze/unfreeze, and aging analysis.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import for_update
from app.models.inventory import SKU, Inventory, TransactionType
from app.models.warehouse import Location, LocationType, Warehouse, Zone
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import post_movement

_INVENTORY_HOLD = AgentGateSpec(
    action="inventory.hold",
    risk="medium",
    permission="master_data.manage",
    entity_type="inventory",
    token_prefix="inv-hold",
)

_INVENTORY_RELEASE = AgentGateSpec(
    action="inventory.release",
    risk="medium",
    permission="master_data.manage",
    entity_type="inventory",
    token_prefix="inv-release",
)


class InventoryRulesService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ─── Safety Stock & Reorder Alerts ───

    async def check_reorder_alerts(self, warehouse_id: str) -> list[dict]:
        """
        Check all SKUs against their safety stock levels.
        Returns items that are below or near reorder point.

        Safety stock is stored in SKU.attributes["safety_stock"]
        Reorder point = safety stock × 1.5
        """
        result = await self.db.execute(
            select(
                SKU.id,
                SKU.sku_code,
                SKU.name,
                SKU.client_id,
                SKU.attributes,
                func.sum(Inventory.quantity_on_hand - Inventory.quantity_allocated).label(
                    "available"
                ),
            )
            .join(Inventory, Inventory.sku_id == SKU.id)
            .where(Inventory.warehouse_id == warehouse_id)
            .group_by(SKU.id, SKU.sku_code, SKU.name, SKU.client_id, SKU.attributes)
        )

        alerts = []
        for row in result.all():
            attrs = row.attributes or {}
            safety = attrs.get("safety_stock", 0)
            if not safety:
                continue

            reorder_point = int(safety * 1.5)
            available = row.available or 0

            if available <= reorder_point:
                level = "critical" if available <= safety else "warning"
                alerts.append(
                    {
                        "sku_id": row.id,
                        "sku_code": row.sku_code,
                        "name": row.name,
                        "client_id": row.client_id,
                        "available": available,
                        "safety_stock": safety,
                        "reorder_point": reorder_point,
                        "level": level,
                        "shortfall": max(0, reorder_point - available),
                    }
                )

        alerts.sort(key=lambda a: a["available"])
        return alerts

    async def set_safety_stock(self, sku_id: str, safety_stock: int) -> dict:
        """Set safety stock level for a SKU."""
        result = await self.db.execute(select(SKU).where(SKU.id == sku_id))
        sku = result.scalar_one()
        attrs = sku.attributes or {}
        attrs["safety_stock"] = safety_stock
        sku.attributes = attrs
        await self.db.flush()
        return {"sku_id": sku_id, "safety_stock": safety_stock}

    # ─── Putaway Rules Engine ───

    async def _get_planner_rules(self, warehouse_id: str) -> dict:
        result = await self.db.execute(
            select(Warehouse.address).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == self.tenant_id,
            )
        )
        address = result.scalar_one_or_none() or {}
        return address.get("_planner_rules", {})

    async def suggest_putaway_location(
        self,
        warehouse_id: str,
        sku_id: str,
        quantity: int,
    ) -> list[dict]:
        """
        Smart putaway suggestion based on rules:
        1. Same SKU consolidation (same product together)
        2. Zone rules: hazmat → hazmat zone, cold → cold zone
        3. ABC velocity: fast movers near shipping dock (low pick_sequence)
        4. Weight/volume check: don't exceed location capacity
        5. Empty available locations as fallback
        """
        suggestions = []
        planner_rules = await self._get_planner_rules(warehouse_id)

        # Get SKU attributes
        sku_result = await self.db.execute(select(SKU).where(SKU.id == sku_id))
        sku = sku_result.scalar_one_or_none()
        if not sku:
            return []

        # Rule 1: Consolidate with existing same-SKU inventory
        existing = await self.db.execute(
            select(Inventory.location_id, Location.barcode, Location.aisle, Location.rack)
            .join(Location, Location.id == Inventory.location_id)
            .where(
                Inventory.warehouse_id == warehouse_id,
                Inventory.sku_id == sku_id,
                Inventory.quantity_on_hand > 0,
                Location.current_status != "blocked",
            )
            .limit(2)
        )
        for row in existing.all():
            suggestions.append(
                {
                    "location_id": row.location_id,
                    "barcode": row.barcode,
                    "address": f"{row.aisle}-{row.rack}",
                    "reason": "consolidate",
                    "priority": 1,
                }
            )

        # Rule 2: Zone-based rules
        target_zone_code = None
        if sku.is_hazmat and planner_rules.get("separate_hazmat", True):
            target_zone_code = "HAZ"
        elif (sku.attributes or {}).get("cold_chain") and planner_rules.get(
            "separate_cold_chain", True
        ):
            target_zone_code = "COLD"

        if target_zone_code:
            zone_locs = await self.db.execute(
                select(Location)
                .join(Zone, Zone.id == Location.zone_id)
                .where(
                    Location.warehouse_id == warehouse_id,
                    Zone.code == target_zone_code,
                    Location.current_status == "available",
                    Location.location_type == LocationType.STORAGE.value,
                )
                .limit(2)
            )
            for loc in zone_locs.scalars():
                suggestions.append(
                    {
                        "location_id": loc.id,
                        "barcode": loc.barcode,
                        "address": f"{loc.aisle}-{loc.rack}-{loc.level}",
                        "reason": f"zone_rule:{target_zone_code}",
                        "priority": 2,
                    }
                )

        # Rule 3 & 5: Empty locations sorted by pick_sequence (near dock = low seq)
        attrs = sku.attributes or {}
        velocity = str(attrs.get("velocity", "")).lower()
        is_fast = attrs.get("fast_mover") is True or velocity in {"a", "fast"}
        is_slow = attrs.get("slow_mover") is True or velocity in {"c", "slow"}
        threshold = float(planner_rules.get("heavy_item_threshold_kg", 20.0))
        is_heavy = bool(sku.weight_kg and float(sku.weight_kg) >= threshold)

        empty_query = select(Location).where(
            Location.warehouse_id == warehouse_id,
            Location.current_status == "available",
            Location.location_type == LocationType.STORAGE.value,
        )

        if planner_rules.get("heavy_items_low", True) and is_heavy:
            empty_query = empty_query.order_by(Location.level.asc(), Location.pick_sequence.asc())
        elif planner_rules.get("slow_movers_deep", True) and is_slow:
            empty_query = empty_query.order_by(desc(Location.pick_sequence))
        elif planner_rules.get("fast_movers_front", True) and is_fast:
            empty_query = empty_query.order_by(Location.pick_sequence.asc())
        else:
            empty_query = empty_query.order_by(Location.pick_sequence.asc())

        empty_locs = await self.db.execute(empty_query.limit(5 - len(suggestions)))
        for loc in empty_locs.scalars():
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
                    "priority": 3,
                }
            )

        # Deduplicate and sort by priority
        seen = set()
        unique = []
        for s in sorted(suggestions, key=lambda x: x["priority"]):
            if s["location_id"] not in seen:
                seen.add(s["location_id"])
                unique.append(s)
        return unique[:5]

    # ─── Inventory Freeze/Unfreeze ───

    async def freeze_inventory(self, inventory_id: str, reason: str, user_id: str) -> dict:
        """Freeze inventory — mark as damaged/held, preventing allocation."""
        result = await self.db.execute(
            for_update(
                select(Inventory).where(
                    Inventory.id == inventory_id,
                    Inventory.tenant_id == self.tenant_id,
                )
            )
        )
        inv = result.scalar_one()
        frozen_qty = max(0, inv.quantity_on_hand - inv.quantity_allocated - inv.quantity_damaged)
        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=inv.client_id,
            transaction_type=TransactionType.ADJUST.value,
            sku_id=inv.sku_id,
            location_id=inv.location_id,
            quantity_change=0,
            inventory=inv,
            delta_damaged=frozen_qty,
            performed_by=user_id,
            notes=f"Inventory hold: {frozen_qty}. Reason: {reason}",
        )
        return {
            "inventory_id": inventory_id,
            "frozen_quantity": frozen_qty,
            "reason": reason,
        }

    async def preview_freeze_inventory(
        self,
        inventory_id: str,
        reason: str,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"inventory_id": inventory_id, "reason": reason}
        endpoint = "POST /api/v1/inventory/rules/freeze"
        entity = {"type": "inventory", "id": inventory_id, "inventory_id": inventory_id}
        state_before = await self._inventory_hold_state(inventory_id)
        if state_before.get("inventory_status") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")
        if not reason.strip():
            return agent_preview.blocked_preview(
                _INVENTORY_HOLD,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="provide_hold_reason",
                result={
                    "what_happened": "Inventory hold needs a reason.",
                    "why_blocked": "inventory_hold_reason_required",
                    "recommended_action": "Add a quality or operational hold reason.",
                    "safe_commands": ["wms inventory hold --dry-run --reason REASON"],
                },
            )

        # No savepoint dry run here: the hold's projected state is a pure
        # arithmetic delta, so the preview computes state_after directly.
        available_to_hold = max(
            0,
            int(state_before.get("quantity_on_hand") or 0)
            - int(state_before.get("quantity_allocated") or 0)
            - int(state_before.get("quantity_damaged") or 0),
        )
        state_after = {
            **state_before,
            "quantity_damaged": int(state_before.get("quantity_damaged") or 0) + available_to_hold,
            "held_quantity": available_to_hold,
        }
        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _INVENTORY_HOLD,
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
                    "held_quantity": available_to_hold,
                    "reason": reason,
                }
            ],
            impact={"quantity_damaged_delta": available_to_hold},
            result={
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms inventory hold --dry-run --live-preview",
                    "wms inventory lookup --query SKU",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_freeze_inventory_with_token(
        self,
        inventory_id: str,
        reason: str,
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _INVENTORY_HOLD,
            confirmation_token,
            message="An inventory hold token is required before the agent can write.",
        )

        preview = await self.preview_freeze_inventory(
            inventory_id=inventory_id,
            reason=reason,
            user_id=user_id,
            persist_evidence=False,
        )
        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _INVENTORY_HOLD,
            entity_id=inventory_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The inventory hold token no longer matches the current preview.",
        )

        result = await self.freeze_inventory(inventory_id, reason, user_id)
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _INVENTORY_HOLD,
            evidence=evidence,
            ok=True,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._inventory_hold_state(inventory_id),
            payload_hash=payload_hash,
            next_action="review_inventory_hold_or_return_to_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

    async def _inventory_hold_state(self, inventory_id: str) -> dict:
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
        }

    async def unfreeze_inventory(
        self,
        inventory_id: str,
        quantity: int,
        reason: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Unfreeze (release) previously frozen inventory."""
        result = await self.db.execute(
            for_update(
                select(Inventory).where(
                    Inventory.id == inventory_id,
                    Inventory.tenant_id == self.tenant_id,
                )
            )
        )
        inv = result.scalar_one()
        if quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Release quantity must be greater than zero",
            )
        release = min(quantity, inv.quantity_damaged)
        await post_movement(
            self.db,
            tenant_id=self.tenant_id,
            client_id=inv.client_id,
            transaction_type=TransactionType.ADJUST.value,
            sku_id=inv.sku_id,
            location_id=inv.location_id,
            quantity_change=0,
            inventory=inv,
            delta_damaged=-release,
            performed_by=user_id,
            notes=f"Inventory release: {release}. Reason: {reason or 'Not provided'}",
        )
        return {"inventory_id": inventory_id, "released": release, "reason": reason}

    async def preview_unfreeze_inventory(
        self,
        inventory_id: str,
        quantity: int,
        reason: str,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"inventory_id": inventory_id, "quantity": quantity, "reason": reason}
        endpoint = "POST /api/v1/inventory/rules/unfreeze"
        entity = {"type": "inventory", "id": inventory_id, "inventory_id": inventory_id}
        state_before = await self._inventory_hold_state(inventory_id)
        if state_before.get("inventory_status") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found")
        if quantity <= 0:
            return agent_preview.blocked_preview(
                _INVENTORY_RELEASE,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="enter_release_quantity",
                result={
                    "what_happened": "Inventory release needs a positive quantity.",
                    "why_blocked": "inventory_release_quantity_required",
                    "recommended_action": "Enter the held quantity to release.",
                    "safe_commands": ["wms inventory release --dry-run --quantity QTY"],
                },
            )
        if not reason.strip():
            return agent_preview.blocked_preview(
                _INVENTORY_RELEASE,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="provide_release_reason",
                result={
                    "what_happened": "Inventory release needs a reason.",
                    "why_blocked": "inventory_release_reason_required",
                    "recommended_action": "Add the reason this held inventory is safe to release.",
                    "safe_commands": ["wms inventory release --dry-run --reason REASON"],
                },
            )

        held_quantity = int(state_before.get("quantity_damaged") or 0)
        if held_quantity <= 0:
            return agent_preview.blocked_preview(
                _INVENTORY_RELEASE,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="choose_held_inventory",
                result={
                    "what_happened": "There is no held inventory to release.",
                    "why_blocked": "inventory_release_no_held_quantity",
                    "recommended_action": "Choose another held inventory row or return to inventory lookup.",
                    "safe_commands": ["wms inventory lookup --query SKU"],
                },
            )

        # No savepoint dry run here: the release's projected state is a pure
        # arithmetic delta, so the preview computes state_after directly.
        release_quantity = min(quantity, held_quantity)
        state_after = {
            **state_before,
            "quantity_damaged": held_quantity - release_quantity,
            "released_quantity": release_quantity,
        }
        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _INVENTORY_RELEASE,
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
                    "released_quantity": release_quantity,
                    "reason": reason,
                }
            ],
            impact={"quantity_damaged_delta": -release_quantity},
            result={
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms inventory release --dry-run --live-preview",
                    "wms inventory lookup --query SKU",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_unfreeze_inventory_with_token(
        self,
        inventory_id: str,
        quantity: int,
        reason: str,
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _INVENTORY_RELEASE,
            confirmation_token,
            message="An inventory release token is required before the agent can write.",
        )

        preview = await self.preview_unfreeze_inventory(
            inventory_id=inventory_id,
            quantity=quantity,
            reason=reason,
            user_id=user_id,
            persist_evidence=False,
        )
        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _INVENTORY_RELEASE,
            entity_id=inventory_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The inventory release token no longer matches the current preview.",
        )

        result = await self.unfreeze_inventory(inventory_id, quantity, reason, user_id)
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _INVENTORY_RELEASE,
            evidence=evidence,
            ok=True,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._inventory_hold_state(inventory_id),
            payload_hash=payload_hash,
            next_action="review_inventory_release_or_return_to_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

    # ─── Aging / Slow-Moving Analysis ───

    async def get_aging_report(self, warehouse_id: str, days_threshold: int = 90) -> list[dict]:
        """
        Inventory aging report — items sitting in warehouse longer than threshold.
        Helps identify slow movers for markdowns or returns to vendor.
        """
        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)

        result = await self.db.execute(
            select(Inventory, SKU)
            .join(SKU, SKU.id == Inventory.sku_id)
            .where(
                Inventory.warehouse_id == warehouse_id,
                Inventory.quantity_on_hand > 0,
                Inventory.received_at < cutoff,
            )
            .order_by(Inventory.received_at)
        )

        return [
            {
                "sku_code": sku.sku_code,
                "name": sku.name,
                "client_id": inv.client_id,
                "location_id": inv.location_id,
                "quantity": inv.quantity_on_hand,
                "received_at": inv.received_at.isoformat() if inv.received_at else "",
                "days_in_warehouse": (datetime.now(UTC) - inv.received_at.replace(tzinfo=UTC)).days
                if inv.received_at
                else 0,
            }
            for inv, sku in result.all()
        ]
