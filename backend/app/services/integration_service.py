"""
Integration Service — Shopify and Amazon order sync.

Handles:
1. Shopify webhook: receives order.created events, creates OutboundOrder
2. Shopify polling: fetches unfulfilled orders periodically
3. Amazon SP-API: fetches unshipped orders, reports fulfillment
4. Generic webhook: outbound events (order_shipped, inventory_updated)

Each integration is configured per-client with credentials stored in client.settings.
"""

import hashlib
import hmac

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.inventory import SKU
from app.models.order import OutboundOrder, OutboundOrderLine, OutboundStatus
from app.services.outbound_readiness import refresh_outbound_readiness_projection


class ShopifyService:
    """Handles Shopify order sync for a specific client."""

    def __init__(self, db: AsyncSession, tenant_id: str, client_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client_id = client_id

    async def get_config(self) -> dict | None:
        """Load Shopify credentials from client settings."""
        result = await self.db.execute(select(Client).where(Client.id == self.client_id))
        client = result.scalar_one_or_none()
        if not client or not client.settings:
            return None
        return client.settings.get("shopify")

    def verify_webhook(self, body: bytes, hmac_header: str, secret: str) -> bool:
        """Verify Shopify webhook signature (HMAC-SHA256)."""
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, hmac_header)

    async def process_order_webhook(self, order_data: dict, warehouse_id: str) -> OutboundOrder:
        """
        Process a Shopify order.created webhook payload.
        Creates an OutboundOrder with lines mapped from Shopify line items.
        """
        shopify_id = str(order_data["id"])
        order_number = order_data.get("name", f"SHOP-{shopify_id}")

        # Check if already imported (idempotency)
        existing = await self.db.execute(
            select(OutboundOrder).where(
                OutboundOrder.tenant_id == self.tenant_id,
                OutboundOrder.reference_number == shopify_id,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one_or_none()

        # Map shipping address
        ship_addr = order_data.get("shipping_address", {})
        address = {
            "street": f"{ship_addr.get('address1', '')} {ship_addr.get('address2', '')}".strip(),
            "city": ship_addr.get("city", ""),
            "state": ship_addr.get("province_code", ""),
            "zip": ship_addr.get("zip", ""),
            "country": ship_addr.get("country_code", "US"),
        }

        order = OutboundOrder(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            warehouse_id=warehouse_id,
            order_number=order_number,
            reference_number=shopify_id,
            status=OutboundStatus.PENDING.value,
            channel="shopify",
            ship_to_name=f"{ship_addr.get('first_name', '')} {ship_addr.get('last_name', '')}".strip(),
            ship_to_address=address,
            extra_data={"shopify_order_id": shopify_id},
        )
        self.db.add(order)
        await self.db.flush()

        # Map line items — match by SKU code
        for item in order_data.get("line_items", []):
            sku_code = item.get("sku", "")
            sku_result = await self.db.execute(
                select(SKU).where(
                    SKU.tenant_id == self.tenant_id,
                    SKU.client_id == self.client_id,
                    SKU.sku_code == sku_code,
                )
            )
            sku = sku_result.scalar_one_or_none()

            if sku:
                line = OutboundOrderLine(
                    tenant_id=self.tenant_id,
                    order_id=order.id,
                    sku_id=sku.id,
                    quantity_ordered=item.get("quantity", 1),
                )
                self.db.add(line)

        await self.db.flush()
        await refresh_outbound_readiness_projection(self.db, self.tenant_id, order)
        return order

    async def report_fulfillment(self, order: OutboundOrder) -> dict:
        """Report fulfillment back to Shopify (creates fulfillment in Shopify)."""
        config = await self.get_config()
        if not config:
            return {"success": False, "error": "Shopify not configured"}

        shopify_order_id = order.reference_number
        shop_domain = config["shop_domain"]
        access_token = config["access_token"]

        url = f"https://{shop_domain}/admin/api/2024-01/orders/{shopify_order_id}/fulfillments.json"

        payload = {
            "fulfillment": {
                "tracking_number": order.tracking_number,
                "tracking_company": order.carrier,
                "notify_customer": True,
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers={"X-Shopify-Access-Token": access_token},
            )

        return {
            "success": response.status_code in (200, 201),
            "shopify_status": response.status_code,
        }


class AmazonService:
    """Handles Amazon SP-API order sync for a specific client."""

    def __init__(self, db: AsyncSession, tenant_id: str, client_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client_id = client_id

    async def get_config(self) -> dict | None:
        result = await self.db.execute(select(Client).where(Client.id == self.client_id))
        client = result.scalar_one_or_none()
        if not client or not client.settings:
            return None
        return client.settings.get("amazon")

    async def import_orders(self, warehouse_id: str) -> list[str]:
        """
        Fetch unshipped orders from Amazon SP-API and create OutboundOrders.
        This is called periodically by a Celery task.

        Returns list of created order IDs.
        """
        config = await self.get_config()
        if not config:
            return []

        # Amazon SP-API call (simplified — real implementation needs OAuth + signing)
        # GET /orders/v0/orders?MarketplaceIds=...&OrderStatuses=Unshipped
        # For now, return empty — actual API integration requires Amazon credentials setup
        return []

    async def report_shipment(self, order: OutboundOrder) -> dict:
        """Report shipment to Amazon via SP-API feeds."""
        config = await self.get_config()
        if not config:
            return {"success": False, "error": "Amazon not configured"}

        # Submit shipment confirmation feed
        # POST /feeds/2021-06-30/feeds (POST_ORDER_FULFILLMENT_DATA)
        # Actual implementation requires Amazon Selling Partner API auth
        return {"success": False, "error": "Amazon SP-API integration pending"}
