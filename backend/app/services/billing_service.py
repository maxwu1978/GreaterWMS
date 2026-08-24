"""
Billing Service — the revenue engine for 3PL operators.

Reads InventoryTransactions and daily inventory snapshots within a billing period,
applies the client's RateCard rules, and generates BillingLineItems.

Charge types:
- Storage: daily pallet/case count × rate (snapshot-based)
- Receiving: inbound units/pallets counted from transactions
- Picking: pick orders/lines/units counted from transactions
- Shipping: handling per order from transactions
- Special handling: hazmat surcharge, oversize, etc.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import (
    BillingLineItem,
    BillingPeriod,
    Invoice,
    InvoiceStatus,
    RateCard,
)
from app.models.client import Client
from app.models.inventory import Inventory, InventoryTransaction
from app.models.tenant import Tenant


class BillingService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def get_active_rate_card(self, client_id: str, as_of: date) -> RateCard | None:
        """Find the active rate card for a client on a given date."""
        result = await self.db.execute(
            select(RateCard)
            .where(
                RateCard.tenant_id == self.tenant_id,
                RateCard.client_id == client_id,
                RateCard.is_active == True,  # noqa: E712
                RateCard.effective_from <= as_of,
                or_(RateCard.effective_to.is_(None), RateCard.effective_to >= as_of),
            )
            .order_by(RateCard.effective_from.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_billing_period(
        self,
        client_id: str,
        period_start: date,
        period_end: date,
    ) -> BillingPeriod:
        """Create a new billing period for a client."""
        period = BillingPeriod(
            tenant_id=self.tenant_id,
            client_id=client_id,
            period_start=period_start,
            period_end=period_end,
            status="open",
        )
        self.db.add(period)
        await self.db.flush()
        return period

    async def calculate_charges(
        self,
        client_id: str,
        period_id: str,
        period_start: date,
        period_end: date,
    ) -> list[dict]:
        """
        Calculate all charges for a client within a billing period.
        Returns a list of charge summaries.
        """
        rate_card = await self.get_active_rate_card(client_id, period_start)
        if not rate_card:
            return [{"error": "No active rate card found for this client"}]

        rules = rate_card.rules
        charges: list[dict] = []

        # 1. Storage charges — based on current inventory (simplified: end-of-period snapshot)
        storage_charges = await self._calc_storage(client_id, rules, period_start, period_end)
        charges.extend(storage_charges)

        # 2. Receiving charges — count inbound transactions in period
        recv_charges = await self._calc_receiving(client_id, rules, period_start, period_end)
        charges.extend(recv_charges)

        # 3. Picking charges — count pick transactions in period
        pick_charges = await self._calc_picking(client_id, rules, period_start, period_end)
        charges.extend(pick_charges)

        # 4. Shipping handling — count ship transactions in period
        ship_charges = await self._calc_shipping(client_id, rules, period_start, period_end)
        charges.extend(ship_charges)

        # 5. Apply minimum monthly charge
        minimum = Decimal(str(rules.get("minimum_monthly", 0)))
        total = sum(Decimal(str(c["total_amount"])) for c in charges)
        if minimum > 0 and total < minimum:
            charges.append(
                {
                    "charge_type": "minimum_adjustment",
                    "description": f"Minimum monthly charge adjustment (min ${minimum})",
                    "quantity": 1,
                    "unit_price": float(minimum - total),
                    "total_amount": float(minimum - total),
                }
            )

        # Persist as BillingLineItems
        for charge in charges:
            if "error" in charge:
                continue
            item = BillingLineItem(
                tenant_id=self.tenant_id,
                billing_period_id=period_id,
                charge_type=charge["charge_type"],
                description=charge["description"],
                quantity=charge["quantity"],
                unit_price=charge["unit_price"],
                total_amount=charge["total_amount"],
            )
            self.db.add(item)

        await self.db.flush()
        return charges

    async def _calc_storage(
        self, client_id: str, rules: dict, start: date, end: date
    ) -> list[dict]:
        """Calculate storage charges based on inventory snapshot."""
        charges = []
        days = (end - start).days or 1

        # Count pallets (simplified: each inventory record with qty > 0 = 1 pallet)
        pallet_rate = rules.get("storage_per_pallet_day")
        if pallet_rate:
            result = await self.db.execute(
                select(func.count(Inventory.id)).where(
                    Inventory.tenant_id == self.tenant_id,
                    Inventory.client_id == client_id,
                    Inventory.quantity_on_hand > 0,
                )
            )
            pallet_count = result.scalar() or 0
            if pallet_count > 0:
                # pallet-days = pallets × days in period
                pallet_days = pallet_count * days
                total = float(Decimal(str(pallet_rate)) * pallet_days)
                charges.append(
                    {
                        "charge_type": "storage",
                        "description": f"Pallet storage: {pallet_count} pallets × {days} days @ ${pallet_rate}/day",
                        "quantity": pallet_days,
                        "unit_price": pallet_rate,
                        "total_amount": total,
                    }
                )

        return charges

    async def _calc_receiving(
        self, client_id: str, rules: dict, start: date, end: date
    ) -> list[dict]:
        """Calculate receiving charges from inbound transactions."""
        charges = []

        # Count total received units
        result = await self.db.execute(
            select(func.sum(InventoryTransaction.quantity_change)).where(
                InventoryTransaction.tenant_id == self.tenant_id,
                InventoryTransaction.client_id == client_id,
                InventoryTransaction.transaction_type == "receive",
                InventoryTransaction.performed_at
                >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                InventoryTransaction.performed_at
                <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
            )
        )
        total_units = result.scalar() or 0

        per_unit = rules.get("receiving_per_unit")
        if per_unit and total_units > 0:
            total = float(Decimal(str(per_unit)) * total_units)
            charges.append(
                {
                    "charge_type": "receiving",
                    "description": f"Receiving: {total_units} units @ ${per_unit}/unit",
                    "quantity": int(total_units),
                    "unit_price": per_unit,
                    "total_amount": total,
                }
            )

        return charges

    async def _calc_picking(
        self, client_id: str, rules: dict, start: date, end: date
    ) -> list[dict]:
        """Calculate picking charges from outbound transactions."""
        charges = []

        # Count pick transactions (each = one pick line)
        result = await self.db.execute(
            select(func.count(InventoryTransaction.id)).where(
                InventoryTransaction.tenant_id == self.tenant_id,
                InventoryTransaction.client_id == client_id,
                InventoryTransaction.transaction_type == "pick",
                InventoryTransaction.performed_at
                >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                InventoryTransaction.performed_at
                <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
            )
        )
        pick_lines = result.scalar() or 0

        per_line = rules.get("pick_per_line")
        if per_line and pick_lines > 0:
            total = float(Decimal(str(per_line)) * pick_lines)
            charges.append(
                {
                    "charge_type": "pick",
                    "description": f"Picking: {pick_lines} lines @ ${per_line}/line",
                    "quantity": int(pick_lines),
                    "unit_price": per_line,
                    "total_amount": total,
                }
            )

        # Count unique orders (pick_per_order)
        per_order = rules.get("pick_per_order")
        if per_order:
            result = await self.db.execute(
                select(func.count(func.distinct(InventoryTransaction.reference_id))).where(
                    InventoryTransaction.tenant_id == self.tenant_id,
                    InventoryTransaction.client_id == client_id,
                    InventoryTransaction.transaction_type == "pick",
                    InventoryTransaction.reference_type == "outbound_order",
                    InventoryTransaction.performed_at
                    >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                    InventoryTransaction.performed_at
                    <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
                )
            )
            order_count = result.scalar() or 0
            if order_count > 0:
                total = float(Decimal(str(per_order)) * order_count)
                charges.append(
                    {
                        "charge_type": "pick_order",
                        "description": f"Pick order handling: {order_count} orders @ ${per_order}/order",
                        "quantity": int(order_count),
                        "unit_price": per_order,
                        "total_amount": total,
                    }
                )

        return charges

    async def _calc_shipping(
        self, client_id: str, rules: dict, start: date, end: date
    ) -> list[dict]:
        """Calculate shipping handling charges."""
        charges = []

        per_order = rules.get("shipping_handling_per_order")
        if per_order:
            result = await self.db.execute(
                select(func.count(func.distinct(InventoryTransaction.reference_id))).where(
                    InventoryTransaction.tenant_id == self.tenant_id,
                    InventoryTransaction.client_id == client_id,
                    InventoryTransaction.transaction_type == "ship",
                    InventoryTransaction.performed_at
                    >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
                    InventoryTransaction.performed_at
                    <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
                )
            )
            ship_count = result.scalar() or 0
            if ship_count > 0:
                total = float(Decimal(str(per_order)) * ship_count)
                charges.append(
                    {
                        "charge_type": "shipping_handling",
                        "description": f"Shipping handling: {ship_count} orders @ ${per_order}/order",
                        "quantity": int(ship_count),
                        "unit_price": per_order,
                        "total_amount": total,
                    }
                )

        return charges

    async def generate_invoice(
        self,
        client_id: str,
        period_id: str,
        invoice_number: str,
    ) -> Invoice:
        """Generate an invoice from a billing period's line items."""
        # Sum up line items
        result = await self.db.execute(
            select(
                func.sum(BillingLineItem.total_amount),
                func.count(BillingLineItem.id),
            ).where(
                BillingLineItem.tenant_id == self.tenant_id,
                BillingLineItem.billing_period_id == period_id,
            )
        )
        row = result.one()
        subtotal = float(row[0] or 0)
        line_item_count = int(row[1] or 0)

        if line_item_count <= 0:
            raise ValueError("No billable line items found for this billing period")

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        tenant = tenant_result.scalar_one()
        client_result = await self.db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.tenant_id == self.tenant_id,
            )
        )
        client = client_result.scalar_one()

        tenant_billing_profile = dict((tenant.settings or {}).get("billing_profile") or {})
        client_billing_profile = dict((client.settings or {}).get("billing_profile") or {})
        tax_region = (
            client_billing_profile.get("tax_region")
            or tenant_billing_profile.get("tax_region")
            or "eu"
        )
        payment_terms_days = int(
            client_billing_profile.get("payment_terms_days")
            or tenant_billing_profile.get("payment_terms_days")
            or 0
        )
        currency = (
            client_billing_profile.get("currency")
            or tenant_billing_profile.get("currency")
            or "USD"
        )
        tax_rate_pct = _coerce_decimal(
            client_billing_profile.get("tax_rate_pct")
            or tenant_billing_profile.get("tax_rate_pct")
            or 0
        )

        tax_rate = tax_rate_pct / Decimal("100")
        tax_amount_decimal = (Decimal(str(subtotal)) * tax_rate).quantize(Decimal("0.01"))
        subtotal_decimal = Decimal(str(subtotal)).quantize(Decimal("0.01"))
        total_decimal = (subtotal_decimal + tax_amount_decimal).quantize(Decimal("0.01"))
        tax_amount = float(tax_amount_decimal)
        total = float(total_decimal)
        issue_date = date.today()
        due_date = issue_date + timedelta(days=payment_terms_days)
        invoice_note = client_billing_profile.get("invoice_notes") or tenant_billing_profile.get(
            "invoice_notes"
        )
        if (
            tax_region == "us"
            and not client_billing_profile.get("tax_label")
            and not tenant_billing_profile.get("tax_label")
        ):
            client_billing_profile["tax_label"] = "Sales Tax"
        elif not client_billing_profile.get("tax_label") and not tenant_billing_profile.get(
            "tax_label"
        ):
            client_billing_profile["tax_label"] = "VAT"

        invoice = Invoice(
            tenant_id=self.tenant_id,
            client_id=client_id,
            billing_period_id=period_id,
            invoice_number=invoice_number,
            status=InvoiceStatus.DRAFT.value,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total,
            currency=currency,
            issued_date=issue_date,
            due_date=due_date,
            notes=invoice_note or None,
        )
        self.db.add(invoice)

        # Close the billing period
        period_result = await self.db.execute(
            select(BillingPeriod).where(
                BillingPeriod.tenant_id == self.tenant_id,
                BillingPeriod.id == period_id,
            )
        )
        period = period_result.scalar_one()
        period.status = "invoiced"

        await self.db.flush()
        return invoice


def _coerce_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
