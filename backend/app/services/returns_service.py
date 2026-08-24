"""
Returns Service — RMA creation, return receiving, disposition, restocking.

Flow: RMA created → Customer ships back → Receive & inspect → Restock or scrap
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Inventory, TransactionType
from app.models.returns import (
    DispositionType,
    ReturnOrder,
    ReturnOrderLine,
    ReturnStatus,
)
from app.services.inventory_ledger import ensure_inventory, post_movement


class ReturnsService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def create_rma(
        self,
        client_id: str,
        warehouse_id: str,
        rma_number: str,
        lines: list[dict],
        original_order_id: str | None = None,
        reason: str | None = None,
        customer_name: str | None = None,
    ) -> ReturnOrder:
        """Create a Return Merchandise Authorization."""
        rma = ReturnOrder(
            tenant_id=self.tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            rma_number=rma_number,
            original_order_id=original_order_id,
            reason=reason,
            customer_name=customer_name,
            status=ReturnStatus.REQUESTED.value,
        )
        self.db.add(rma)
        await self.db.flush()

        for line_data in lines:
            line = ReturnOrderLine(
                tenant_id=self.tenant_id,
                return_order_id=rma.id,
                sku_id=line_data["sku_id"],
                quantity_expected=line_data["quantity"],
                reason=line_data.get("reason"),
            )
            self.db.add(line)

        await self.db.flush()
        return rma

    async def receive_return(
        self,
        rma_id: str,
        line_id: str,
        quantity_received: int,
        quantity_damaged: int = 0,
        location_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Receive returned items — scan and inspect."""
        result = await self.db.execute(
            select(ReturnOrderLine).where(
                ReturnOrderLine.tenant_id == self.tenant_id,
                ReturnOrderLine.id == line_id,
            )
        )
        line = result.scalar_one()

        line.quantity_received = quantity_received
        line.quantity_damaged = quantity_damaged

        # Update RMA status
        rma_result = await self.db.execute(
            select(ReturnOrder).where(
                ReturnOrder.tenant_id == self.tenant_id, ReturnOrder.id == rma_id
            )
        )
        rma = rma_result.scalar_one()
        if rma.status == ReturnStatus.REQUESTED.value:
            rma.status = ReturnStatus.RECEIVED.value
            rma.received_date = datetime.now(UTC)

        await self.db.flush()
        return {
            "line_id": line_id,
            "received": quantity_received,
            "damaged": quantity_damaged,
            "good": quantity_received - quantity_damaged,
        }

    async def process_disposition(
        self,
        rma_id: str,
        line_id: str,
        disposition: str,
        restock_location_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        Decide what to do with returned items:
        - restock: put back on shelf → creates inventory
        - damaged: mark as damaged
        - scrap: dispose
        """
        result = await self.db.execute(
            select(ReturnOrderLine).where(
                ReturnOrderLine.tenant_id == self.tenant_id,
                ReturnOrderLine.id == line_id,
            )
        )
        line = result.scalar_one()
        line.disposition = disposition
        good_qty = line.quantity_received - line.quantity_damaged

        rma_result = await self.db.execute(
            select(ReturnOrder).where(
                ReturnOrder.tenant_id == self.tenant_id, ReturnOrder.id == rma_id
            )
        )
        rma = rma_result.scalar_one()

        if disposition == DispositionType.RESTOCK.value and good_qty > 0 and restock_location_id:
            # Add back to inventory
            inv_result = await self.db.execute(
                select(Inventory).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.location_id == restock_location_id,
                    Inventory.sku_id == line.sku_id,
                )
            )
            inv = ensure_inventory(
                self.db,
                inv_result.scalar_one_or_none(),
                tenant_id=self.tenant_id,
                client_id=rma.client_id,
                warehouse_id=rma.warehouse_id,
                location_id=restock_location_id,
                sku_id=line.sku_id,
                received_at=datetime.now(UTC),
            )

            line.quantity_restocked = good_qty

            # Restock and record the transaction
            await post_movement(
                self.db,
                tenant_id=self.tenant_id,
                client_id=rma.client_id,
                transaction_type=TransactionType.RETURN.value,
                sku_id=line.sku_id,
                location_id=restock_location_id,
                quantity_change=good_qty,
                inventory=inv,
                delta_on_hand=good_qty,
                to_location_id=restock_location_id,
                reference_type="return_order",
                reference_id=rma_id,
                performed_by=user_id,
                notes=f"Return restocked from RMA {rma.rma_number}",
                flush=False,
            )

        elif disposition == DispositionType.SCRAP.value:
            line.quantity_scrapped = line.quantity_received

        elif disposition == DispositionType.DAMAGED.value:
            line.quantity_damaged = line.quantity_received

        # Check if all lines are disposed → complete RMA
        all_lines = await self.db.execute(
            select(ReturnOrderLine).where(
                ReturnOrderLine.tenant_id == self.tenant_id,
                ReturnOrderLine.return_order_id == rma_id,
            )
        )
        all_disposed = all(
            return_line.disposition is not None for return_line in all_lines.scalars()
        )
        if all_disposed:
            rma.status = ReturnStatus.COMPLETED.value
            rma.completed_date = datetime.now(UTC)

        await self.db.flush()
        return {
            "disposition": disposition,
            "restocked": line.quantity_restocked,
            "scrapped": line.quantity_scrapped,
            "damaged": line.quantity_damaged,
            "rma_status": rma.status,
        }
