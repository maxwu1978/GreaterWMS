"""
Shipping Service — packing verification, ship confirm, and tracking.

Flow: Order picked → Pack & verify → Generate shipping label → Ship confirm → Notify client
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import TransactionType
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.services import agent_preview
from app.services.agent_preview import AgentGateSpec
from app.services.inventory_ledger import post_movement
from app.services.outbound_readiness import apply_outbound_readiness_projection

_SHIPPING_PACK = AgentGateSpec(
    action="shipping.pack",
    risk="medium",
    permission="fulfillment.execute",
    entity_type="outbound_order",
    token_prefix="pack-confirm",
)

_SHIPPING_SHIP = AgentGateSpec(
    action="shipping.ship",
    risk="medium",
    permission="fulfillment.execute",
    entity_type="outbound_order",
    token_prefix="ship-confirm",
)


class ShippingService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def _get_order(self, order_id: str) -> OutboundOrder:
        order = await self.db.scalar(
            select(OutboundOrder).where(
                OutboundOrder.id == order_id,
                OutboundOrder.tenant_id == self.tenant_id,
            )
        )
        if not order:
            raise HTTPException(status_code=404, detail="Outbound order not found")
        return order

    async def verify_pack(
        self,
        order_id: str,
        scanned_items: list[dict],
        user_id: str,
    ) -> dict:
        """
        Packing verification — operator scans each item into the box.
        Compares scanned items against order lines to catch errors before shipping.

        scanned_items: [{"sku_id": "...", "quantity": 5}, ...]
        """
        order = await self._get_order(order_id)
        if order.status not in {OutboundStatus.PICKED.value, OutboundStatus.PACKING.value}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Only picked outbound orders can be packed. "
                    f"This outbound order is currently {order.status}."
                ),
            )

        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        lines = {line.sku_id: line for line in lines_result.scalars()}

        scanned_by_sku: dict[str, int] = {}
        for item in scanned_items:
            sku_id = item["sku_id"]
            scanned_qty = int(item["quantity"])
            scanned_by_sku[sku_id] = scanned_by_sku.get(sku_id, 0) + scanned_qty

        errors = []
        for sku_id in scanned_by_sku:
            if sku_id not in lines:
                errors.append({"sku_id": sku_id, "error": "not_in_order"})
                continue

        for sku_id, line in lines.items():
            expected = line.quantity_picked
            scanned_qty = scanned_by_sku.get(sku_id, 0)
            if scanned_qty != expected:
                errors.append(
                    {
                        "sku_id": sku_id,
                        "error": "quantity_mismatch",
                        "expected": expected,
                        "scanned": scanned_qty,
                    }
                )

        if not errors:
            order.status = OutboundStatus.PACKED.value
        apply_outbound_readiness_projection(order)

        await self.db.flush()
        return {
            "order_id": order_id,
            "verified": len(errors) == 0,
            "errors": errors,
        }

    async def ship_confirm(
        self,
        order_id: str,
        carrier: str,
        tracking_number: str,
        service_level: str | None = None,
        shipping_cost: float | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        Confirm shipment — carrier picked up the package.
        Records final ship transaction and updates order status.
        """
        order = await self._get_order(order_id)
        if order.status != OutboundStatus.PACKED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Only packed outbound orders can be shipped. "
                    f"This outbound order is currently {order.status}."
                ),
            )

        order.status = OutboundStatus.SHIPPED.value
        order.carrier = carrier
        order.tracking_number = tracking_number
        order.service_level = service_level
        order.shipping_cost = shipping_cost
        order.shipped_date = datetime.now(UTC)
        apply_outbound_readiness_projection(order)

        # Record ship transactions for each line
        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        for line in lines_result.scalars():
            if line.quantity_picked > 0:
                line.quantity_shipped = line.quantity_picked

                # Ledger-only: stock was already deducted at pick time
                await post_movement(
                    self.db,
                    tenant_id=self.tenant_id,
                    client_id=order.client_id,
                    transaction_type=TransactionType.SHIP.value,
                    sku_id=line.sku_id,
                    location_id=line.pick_location_id or "",
                    quantity_change=-line.quantity_shipped,
                    reference_type="outbound_order",
                    reference_id=order_id,
                    performed_by=user_id,
                    flush=False,
                )

        await self.db.flush()
        return {
            "order_id": order_id,
            "status": "shipped",
            "carrier": carrier,
            "tracking_number": tracking_number,
        }

    async def preview_pack_verification(
        self,
        order_id: str,
        scanned_items: list[dict],
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {"order_id": order_id, "scanned_items": scanned_items}
        endpoint = "POST /api/v1/fulfillment/pack/verify"
        entity = {"type": "outbound_order", "id": order_id, "order_id": order_id}
        state_before = await self._shipping_state(order_id)
        planned_result, state_after = await agent_preview.savepoint_dry_run(
            self.db,
            lambda: self.verify_pack(
                order_id=order_id,
                scanned_items=scanned_items,
                user_id=user_id or "agent-preview",
            ),
            lambda: self._shipping_state(order_id),
        )

        if not planned_result.get("verified"):
            return agent_preview.blocked_preview(
                _SHIPPING_PACK,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="fix_pack_scan_before_confirming",
                result={
                    "what_happened": "Pack verification did not match the outbound order.",
                    "why_blocked": "shipping_pack_verification_failed",
                    "recommended_action": "Review scanned SKUs and quantities, then preview pack again.",
                    "errors": planned_result.get("errors", []),
                    "safe_commands": [
                        "wms shipping pack --dry-run --live-preview",
                        "wms shipping next --dry-run",
                    ],
                },
            )

        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _SHIPPING_PACK,
            entity=entity,
            entity_id=order_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"order_id": order_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "order_id": order_id,
            },
            records=[
                {
                    "type": "outbound_order",
                    "id": order_id,
                    "order_number": state_before.get("order_number"),
                    "status": state_before.get("order_status"),
                    "scanned_items": scanned_items,
                }
            ],
            impact={
                "order_status": "packed",
                "verified": True,
            },
            result={
                "message": "No backend write was performed.",
                "planned_result": planned_result,
                "safe_commands": [
                    "wms shipping pack --dry-run --live-preview",
                    "wms shipping ship --dry-run --order-id ORDER --carrier CARRIER --tracking-number TRACKING",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_pack_with_token(
        self,
        order_id: str,
        scanned_items: list[dict],
        confirmation_token: str,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _SHIPPING_PACK,
            confirmation_token,
            message="A pack confirmation token is required before the agent can write.",
        )

        preview = await self.preview_pack_verification(
            order_id=order_id,
            scanned_items=scanned_items,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _SHIPPING_PACK,
            preview,
            error_code="pack_preview_failed",
            default_message="Pack preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _SHIPPING_PACK,
            entity_id=order_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The pack confirmation token no longer matches the current preview.",
        )

        result = await self.verify_pack(
            order_id=order_id,
            scanned_items=scanned_items,
            user_id=user_id,
        )
        ok = bool(result.get("verified"))
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _SHIPPING_PACK,
            evidence=evidence,
            ok=ok,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._shipping_state(order_id),
            payload_hash=payload_hash,
            next_action="ship_order_or_return_to_shipping_queue",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=None if ok else str(result),
        )

    async def preview_ship_confirmation(
        self,
        order_id: str,
        carrier: str,
        tracking_number: str,
        service_level: str | None = None,
        shipping_cost: float | None = None,
        user_id: str | None = None,
        persist_evidence: bool = True,
    ) -> dict:
        body = {
            "order_id": order_id,
            "carrier": carrier,
            "tracking_number": tracking_number,
            "service_level": service_level,
            "shipping_cost": shipping_cost,
        }
        endpoint = "POST /api/v1/fulfillment/ship/confirm"
        entity = {"type": "outbound_order", "id": order_id, "order_id": order_id}
        state_before = await self._shipping_state(order_id)
        if state_before.get("order_status") != OutboundStatus.PACKED.value:
            return agent_preview.blocked_preview(
                _SHIPPING_SHIP,
                entity=entity,
                state_before=state_before,
                endpoint=endpoint,
                body=body,
                next_action="pack_order_before_shipping",
                result={
                    "what_happened": "Outbound order cannot be shipped yet.",
                    "why_blocked": "shipping_order_not_packed",
                    "recommended_action": "Pack the order first, or choose another packed order.",
                    "safe_commands": [
                        "wms shipping next --dry-run",
                        "wms shipping pack --dry-run --order-id ORDER --sku-id SKU --quantity QTY",
                    ],
                },
            )

        # No savepoint dry run here: the ship projection is fully derivable from
        # the packed order's current state, so the preview computes state_after.
        state_after = {
            **state_before,
            "order_status": OutboundStatus.SHIPPED.value,
            "carrier": carrier,
            "tracking_number": tracking_number,
            "service_level": service_level,
            "shipping_cost": shipping_cost,
            "shipped_date": "set_on_confirm",
            "lines": [
                {
                    **line,
                    "quantity_shipped": line.get("quantity_picked", 0),
                }
                for line in state_before.get("lines", [])
            ],
        }
        return await agent_preview.issue_preview(
            self.db,
            self.tenant_id,
            _SHIPPING_SHIP,
            entity=entity,
            entity_id=order_id,
            endpoint=endpoint,
            body=body,
            hash_scope={"order_id": order_id},
            state_before=state_before,
            state_after=state_after,
            scope={
                "tenant_id": self.tenant_id,
                "warehouse_id": state_before.get("warehouse_id"),
                "order_id": order_id,
            },
            records=[
                {
                    "type": "outbound_order",
                    "id": order_id,
                    "order_number": state_before.get("order_number"),
                    "status": state_before.get("order_status"),
                    "carrier": carrier,
                    "tracking_number": tracking_number,
                }
            ],
            impact={
                "order_status": "shipped",
                "ship_transactions": [
                    {
                        "sku_id": line.get("sku_id"),
                        "quantity_change": -line.get("quantity_picked", 0),
                    }
                    for line in state_before.get("lines", [])
                    if line.get("quantity_picked", 0) > 0
                ],
            },
            result={
                "message": "No backend write was performed.",
                "safe_commands": [
                    "wms shipping ship --dry-run --live-preview",
                    "wms shipping next --dry-run",
                ],
            },
            user_id=user_id,
            persist_evidence=persist_evidence,
        )

    async def confirm_ship_with_token(
        self,
        order_id: str,
        carrier: str,
        tracking_number: str,
        confirmation_token: str,
        service_level: str | None = None,
        shipping_cost: float | None = None,
        user_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        agent_preview.require_confirmation_token(
            _SHIPPING_SHIP,
            confirmation_token,
            message="A shipping confirmation token is required before the agent can write.",
        )

        preview = await self.preview_ship_confirmation(
            order_id=order_id,
            carrier=carrier,
            tracking_number=tracking_number,
            service_level=service_level,
            shipping_cost=shipping_cost,
            user_id=user_id,
            persist_evidence=False,
        )
        agent_preview.require_preview_ok(
            _SHIPPING_SHIP,
            preview,
            error_code="ship_preview_failed",
            default_message="Ship preview failed.",
        )

        payload_hash = preview["confirmation_payload"]["payload_hash"]
        evidence = await agent_preview.match_evidence(
            self.db,
            self.tenant_id,
            _SHIPPING_SHIP,
            entity_id=order_id,
            payload_hash=payload_hash,
            confirmation_token=confirmation_token,
            mismatch_message="The shipping confirmation token no longer matches the current preview.",
        )

        result = await self.ship_confirm(
            order_id=order_id,
            carrier=carrier,
            tracking_number=tracking_number,
            service_level=service_level,
            shipping_cost=shipping_cost,
            user_id=user_id,
        )
        ok = result.get("status") == "shipped"
        return await agent_preview.finalize_confirmation(
            self.db,
            self.tenant_id,
            _SHIPPING_SHIP,
            evidence=evidence,
            ok=ok,
            entity=preview["entity"],
            state_before=preview["state_before"],
            state_after=await self._shipping_state(order_id),
            payload_hash=payload_hash,
            next_action="return_to_shipping_queue_or_dashboard",
            result=result,
            user_id=user_id,
            idempotency_key=idempotency_key,
            failure_reason=None if ok else str(result),
        )

    async def _shipping_state(self, order_id: str) -> dict:
        order = await self.db.scalar(
            select(OutboundOrder).where(
                OutboundOrder.id == order_id,
                OutboundOrder.tenant_id == self.tenant_id,
            )
        )
        if not order:
            return {"order_id": order_id, "order_status": "not_found"}
        lines = (
            await self.db.execute(
                select(OutboundOrderLine)
                .where(
                    OutboundOrderLine.tenant_id == self.tenant_id,
                    OutboundOrderLine.order_id == order_id,
                )
                .order_by(OutboundOrderLine.id.asc())
            )
        ).scalars().all()
        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "warehouse_id": order.warehouse_id,
            "client_id": order.client_id,
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
            "service_level": order.service_level,
            "shipping_cost": float(order.shipping_cost) if order.shipping_cost is not None else None,
            "shipped_date": order.shipped_date.isoformat() if order.shipped_date else None,
            "lines": [
                {
                    "id": line.id,
                    "sku_id": line.sku_id,
                    "pick_location_id": line.pick_location_id,
                    "quantity_ordered": line.quantity_ordered,
                    "quantity_picked": line.quantity_picked,
                    "quantity_shipped": line.quantity_shipped,
                }
                for line in lines
            ],
        }

    async def get_shipment_summary(self, order_id: str) -> dict:
        """Get shipping summary for an order — used by client portal."""
        order = await self._get_order(order_id)

        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        lines = lines_result.scalars().all()

        return {
            "order_id": order_id,
            "order_number": order.order_number,
            "status": order.status,
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
            "shipped_date": order.shipped_date.isoformat() if order.shipped_date else None,
            "lines": [
                {
                    "sku_id": line.sku_id,
                    "ordered": line.quantity_ordered,
                    "shipped": line.quantity_shipped,
                }
                for line in lines
            ],
        }
