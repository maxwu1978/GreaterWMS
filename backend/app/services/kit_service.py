"""
Kit/Bundle Service — manage composite products, check component availability,
and explode kits into individual picks.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import SKU, Inventory
from app.models.kit import Kit, KitComponent


class KitService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def create_kit(
        self,
        client_id: str,
        sku_id: str,
        name: str,
        components: list[dict],
    ) -> Kit:
        """Create a kit/bundle with component SKUs."""
        kit = Kit(
            tenant_id=self.tenant_id,
            client_id=client_id,
            sku_id=sku_id,
            name=name,
        )
        self.db.add(kit)
        await self.db.flush()

        for comp in components:
            self.db.add(
                KitComponent(
                    tenant_id=self.tenant_id,
                    kit_id=kit.id,
                    component_sku_id=comp["sku_id"],
                    quantity=comp["quantity"],
                )
            )
        await self.db.flush()
        return kit

    async def get_kit(self, sku_id: str) -> Kit | None:
        """Get kit definition by its SKU ID."""
        query = select(Kit).where(Kit.sku_id == sku_id, Kit.is_active == True)  # noqa
        # The availability endpoint is reachable by platform admins
        # (tenant_id=None); only scope when a tenant context exists.
        if self.tenant_id:
            query = query.where(Kit.tenant_id == self.tenant_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def explode_kit(self, sku_id: str, quantity: int) -> list[dict]:
        """
        Explode a kit into its component SKUs with quantities.
        Used during order allocation to pick individual components.
        """
        kit = await self.get_kit(sku_id)
        if not kit:
            return [{"sku_id": sku_id, "quantity": quantity}]  # Not a kit, return as-is

        result = await self.db.execute(
            select(KitComponent).where(
                KitComponent.tenant_id == kit.tenant_id,
                KitComponent.kit_id == kit.id,
            )
        )
        return [
            {"sku_id": comp.component_sku_id, "quantity": comp.quantity * quantity}
            for comp in result.scalars()
        ]

    async def check_availability(self, sku_id: str, quantity: int, warehouse_id: str) -> dict:
        """Check if all components have enough stock to fulfill N kits."""
        components = await self.explode_kit(sku_id, quantity)
        results = []
        can_fulfill = True

        for comp in components:
            availability_query = select(
                func.sum(
                    Inventory.quantity_on_hand
                    - Inventory.quantity_allocated
                    - Inventory.quantity_damaged
                )
            ).where(
                Inventory.sku_id == comp["sku_id"],
                Inventory.warehouse_id == warehouse_id,
            )
            if self.tenant_id:
                availability_query = availability_query.where(Inventory.tenant_id == self.tenant_id)
            available = (await self.db.execute(availability_query)).scalar() or 0

            needed = comp["quantity"]
            ok = available >= needed
            if not ok:
                can_fulfill = False

            # Get SKU code for display
            sku_query = select(SKU.sku_code).where(SKU.id == comp["sku_id"])
            if self.tenant_id:
                sku_query = sku_query.where(SKU.tenant_id == self.tenant_id)
            sku_result = await self.db.execute(sku_query)
            sku_code = sku_result.scalar() or comp["sku_id"]

            results.append(
                {
                    "sku_id": comp["sku_id"],
                    "sku_code": sku_code,
                    "needed": needed,
                    "available": available,
                    "sufficient": ok,
                }
            )

        return {
            "can_fulfill": can_fulfill,
            "kits_requested": quantity,
            "components": results,
        }
