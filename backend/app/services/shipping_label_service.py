"""
Shipping Label Service — UPS, FedEx, USPS rate shopping and label generation.

Uses EasyPost API as a unified shipping aggregator (free to sign up, pay-per-label).
EasyPost wraps UPS/FedEx/USPS/DHL into one API — no need for separate integrations.

Alternative: direct UPS/FedEx APIs (more complex, lower per-label cost at volume).
"""

import base64
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.inventory import SKU
from app.models.order import OutboundOrder, OutboundOrderLine
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse

logger = logging.getLogger("wms.shipping")


class ShippingLabelService:
    """Generate shipping labels via EasyPost (or mock for development)."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.api_key = settings.EASYPOST_API_KEY
        self.base_url = "https://api.easypost.com/v2"

    async def get_rates(self, order_id: str) -> dict:
        """
        Get shipping rates from multiple carriers for an order.
        Returns sorted rates (cheapest first) from UPS, FedEx, USPS.
        """
        order, from_addr, to_addr, parcel = await self._build_shipment_data(order_id)

        if not self.api_key:
            # Mock rates for development
            return self._mock_rates(order)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/shipments",
                auth=(self.api_key, ""),
                json={
                    "shipment": {
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "parcel": parcel,
                    }
                },
            )
            data = resp.json()

        if "error" in data:
            return {"success": False, "error": data["error"]}

        shipment_id = data.get("id")
        rates = []
        for rate in data.get("rates", []):
            rates.append(
                {
                    "id": rate["id"],
                    "carrier": rate["carrier"],
                    "service": rate["service"],
                    "rate": float(rate["rate"]),
                    "currency": rate["currency"],
                    "delivery_days": rate.get("delivery_days"),
                    "delivery_date": rate.get("delivery_date"),
                }
            )

        rates.sort(key=lambda r: r["rate"])
        return {
            "success": True,
            "shipment_id": shipment_id,
            "rates": rates,
            "cheapest": rates[0] if rates else None,
        }

    async def buy_label(
        self, order_id: str, rate_id: str | None = None, shipment_id: str | None = None
    ) -> dict:
        """
        Purchase a shipping label. If no rate_id, uses cheapest available rate.
        Returns label PDF (base64) + tracking number.
        """
        if not self.api_key:
            return await self._mock_buy_label(order_id)

        # If no shipment_id, create one first
        if not shipment_id:
            rates_result = await self.get_rates(order_id)
            if not rates_result.get("success"):
                return rates_result
            shipment_id = rates_result["shipment_id"]
            if not rate_id:
                rate_id = rates_result["cheapest"]["id"]

        # Buy the label
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/shipments/{shipment_id}/buy",
                auth=(self.api_key, ""),
                json={"rate": {"id": rate_id}},
            )
            data = resp.json()

        if "error" in data:
            return {"success": False, "error": data["error"]}

        tracking = data.get("tracking_code")
        carrier = data.get("selected_rate", {}).get("carrier", "")
        service = data.get("selected_rate", {}).get("service", "")
        rate = float(data.get("selected_rate", {}).get("rate", 0))
        label_url = data.get("postage_label", {}).get("label_url", "")

        # Download label PDF
        label_pdf_b64 = ""
        if label_url:
            async with httpx.AsyncClient() as client:
                label_resp = await client.get(label_url)
                if label_resp.status_code == 200:
                    label_pdf_b64 = base64.b64encode(label_resp.content).decode()

        # Update order with tracking info
        result = await self.db.execute(
            select(OutboundOrder).where(
                OutboundOrder.tenant_id == self.tenant_id, OutboundOrder.id == order_id
            )
        )
        order = result.scalar_one()
        order.carrier = carrier
        order.tracking_number = tracking
        order.service_level = service
        order.shipping_cost = rate
        # The label is already purchased (real money) — persist tracking immediately
        # so a later failure in the same request can never roll it back.
        await self.db.commit()

        return {
            "success": True,
            "tracking_number": tracking,
            "carrier": carrier,
            "service": service,
            "rate": rate,
            "label_pdf_base64": label_pdf_b64,
            "label_url": label_url,
        }

    async def _build_shipment_data(self, order_id: str) -> tuple:
        """Build EasyPost shipment payload from order data."""
        result = await self.db.execute(
            select(OutboundOrder).where(
                OutboundOrder.tenant_id == self.tenant_id, OutboundOrder.id == order_id
            )
        )
        order = result.scalar_one()

        # From address (warehouse)
        wh_result = await self.db.execute(
            select(Warehouse).where(
                Warehouse.tenant_id == self.tenant_id, Warehouse.id == order.warehouse_id
            )
        )
        wh_result.scalar_one()

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        tenant = tenant_result.scalar_one()
        tenant_addr = tenant.address or {}

        from_addr = {
            "company": tenant.name,
            "street1": tenant_addr.get("street", ""),
            "city": tenant_addr.get("city", ""),
            "state": tenant_addr.get("state", ""),
            "zip": tenant_addr.get("zip", ""),
            "country": tenant_addr.get("country", "US"),
            "phone": tenant.contact_phone or "",
        }

        # To address
        ship_to = order.ship_to_address or {}
        to_addr = {
            "name": order.ship_to_name or "",
            "street1": ship_to.get("street", ""),
            "city": ship_to.get("city", ""),
            "state": ship_to.get("state", ""),
            "zip": ship_to.get("zip", ""),
            "country": ship_to.get("country", "US"),
        }

        # Parcel dimensions (estimate from order lines)
        lines_result = await self.db.execute(
            select(OutboundOrderLine).where(
                OutboundOrderLine.tenant_id == self.tenant_id,
                OutboundOrderLine.order_id == order_id,
            )
        )
        lines = lines_result.scalars().all()

        sku_ids = {line.sku_id for line in lines}
        sku_map: dict[str, SKU] = {}
        if sku_ids:
            sku_result = await self.db.execute(
                select(SKU).where(SKU.tenant_id == self.tenant_id, SKU.id.in_(sku_ids))
            )
            sku_map = {sku.id: sku for sku in sku_result.scalars()}

        total_weight_oz = 0
        for line in lines:
            sku = sku_map.get(line.sku_id)
            if sku and sku.weight_kg:
                total_weight_oz += float(sku.weight_kg) * 35.274 * line.quantity_ordered

        parcel = {
            "length": 12,  # inches — default box
            "width": 10,
            "height": 6,
            "weight": max(total_weight_oz, 8),  # minimum 8 oz
        }

        return order, from_addr, to_addr, parcel

    def _mock_rates(self, order: OutboundOrder) -> dict:
        """Generate mock rates for development (no EasyPost key)."""
        return {
            "success": True,
            "shipment_id": "shp_mock_001",
            "rates": [
                {
                    "id": "rate_usps_ground",
                    "carrier": "USPS",
                    "service": "GroundAdvantage",
                    "rate": 5.99,
                    "currency": "USD",
                    "delivery_days": 5,
                },
                {
                    "id": "rate_ups_ground",
                    "carrier": "UPS",
                    "service": "Ground",
                    "rate": 8.50,
                    "currency": "USD",
                    "delivery_days": 4,
                },
                {
                    "id": "rate_ups_3day",
                    "carrier": "UPS",
                    "service": "3DaySelect",
                    "rate": 14.25,
                    "currency": "USD",
                    "delivery_days": 3,
                },
                {
                    "id": "rate_fedex_ground",
                    "carrier": "FedEx",
                    "service": "GROUND_HOME_DELIVERY",
                    "rate": 9.15,
                    "currency": "USD",
                    "delivery_days": 4,
                },
                {
                    "id": "rate_fedex_express",
                    "carrier": "FedEx",
                    "service": "FEDEX_EXPRESS_SAVER",
                    "rate": 18.90,
                    "currency": "USD",
                    "delivery_days": 2,
                },
                {
                    "id": "rate_ups_next",
                    "carrier": "UPS",
                    "service": "NextDayAir",
                    "rate": 32.50,
                    "currency": "USD",
                    "delivery_days": 1,
                },
            ],
            "cheapest": {
                "id": "rate_usps_ground",
                "carrier": "USPS",
                "service": "GroundAdvantage",
                "rate": 5.99,
                "currency": "USD",
                "delivery_days": 5,
            },
        }

    async def _mock_buy_label(self, order_id: str) -> dict:
        """Generate mock label for development."""
        import random

        tracking = f"1Z999AA1{random.randint(1000000, 9999999)}"

        # Update order
        result = await self.db.execute(
            select(OutboundOrder).where(
                OutboundOrder.tenant_id == self.tenant_id, OutboundOrder.id == order_id
            )
        )
        order = result.scalar_one()
        order.carrier = "UPS"
        order.tracking_number = tracking
        order.service_level = "Ground"
        order.shipping_cost = 8.50
        await self.db.flush()

        # Generate a mock label PDF
        try:
            import io

            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=(288, 432))  # 4x6 label
            styles = getSampleStyleSheet()
            elements = [
                Paragraph("<b>SHIP TO:</b>", styles["Normal"]),
                Paragraph(f"{order.ship_to_name}", styles["Heading2"]),
                Paragraph(f"{(order.ship_to_address or {}).get('street', '')}", styles["Normal"]),
                Paragraph(
                    f"{(order.ship_to_address or {}).get('city', '')}, {(order.ship_to_address or {}).get('state', '')} {(order.ship_to_address or {}).get('zip', '')}",
                    styles["Normal"],
                ),
                Spacer(1, 20),
                Paragraph(f"<b>TRACKING: {tracking}</b>", styles["Heading3"]),
                Paragraph(f"UPS Ground | Order: {order.order_number}", styles["Normal"]),
            ]
            doc.build(elements)
            label_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            label_b64 = ""

        return {
            "success": True,
            "tracking_number": tracking,
            "carrier": "UPS",
            "service": "Ground",
            "rate": 8.50,
            "label_pdf_base64": label_b64,
            "label_url": "",
            "mock": True,
        }
