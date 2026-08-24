"""
Test billing calculation engine.

Verifies that InventoryTransactions are correctly counted and priced
using the client's RateCard rules.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingLineItem, RateCard
from app.models.client import Client
from app.models.inventory import SKU, Inventory, InventoryTransaction
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.billing_service import BillingService


async def setup_billing_data(db: AsyncSession):
    """Set up tenant, client, warehouse, SKU, rate card, and sample transactions."""
    tenant = Tenant(id="t1", name="Billing Test 3PL", code="BT", contact_email="billing@test.com")
    db.add(tenant)

    client = Client(id="c1", tenant_id="t1", name="Billed Client", code="BC")
    db.add(client)

    wh = Warehouse(id="wh1", tenant_id="t1", name="WH1", code="WH1")
    db.add(wh)

    zone = Zone(id="z1", tenant_id="t1", warehouse_id="wh1", name="Z1", code="Z1")
    db.add(zone)

    loc = Location(
        id="l1",
        tenant_id="t1",
        warehouse_id="wh1",
        zone_id="z1",
        barcode="A-01-01-01-01",
        aisle="01",
        rack="01",
        level="01",
        position="01",
        location_type=LocationType.STORAGE.value,
        current_status=LocationStatus.OCCUPIED.value,
    )
    db.add(loc)

    sku = SKU(id="s1", tenant_id="t1", client_id="c1", sku_code="ITEM-001", name="Test Item")
    db.add(sku)

    # Rate card with all charge types
    rc = RateCard(
        tenant_id="t1",
        client_id="c1",
        name="Standard Rate",
        effective_from=date(2026, 1, 1),
        rules={
            "storage_per_pallet_day": 0.85,
            "receiving_per_unit": 0.25,
            "pick_per_line": 0.50,
            "pick_per_order": 2.00,
            "shipping_handling_per_order": 1.50,
            "minimum_monthly": 100.00,
        },
    )
    db.add(rc)

    # Inventory: 3 pallets — distinct LPNs, as receiving/putaway would create them
    # (same location+sku with no LPN merges into one row; uq_inventory_stock_position
    # enforces that)
    for _i in range(3):
        inv = Inventory(
            tenant_id="t1",
            client_id="c1",
            warehouse_id="wh1",
            location_id="l1",
            sku_id="s1",
            lpn=f"PLT-{_i + 1}",
            quantity_on_hand=50,
        )
        db.add(inv)

    # Transactions in March 2026:
    # - Received 200 units
    db.add(
        InventoryTransaction(
            tenant_id="t1",
            client_id="c1",
            transaction_type="receive",
            sku_id="s1",
            location_id="l1",
            quantity_change=200,
            performed_at=datetime(2026, 3, 5, 10, 0, tzinfo=UTC),
        )
    )

    # - Picked 3 lines from 2 orders
    for i, order_id in enumerate(["ord-1", "ord-1", "ord-2"]):
        db.add(
            InventoryTransaction(
                tenant_id="t1",
                client_id="c1",
                transaction_type="pick",
                sku_id="s1",
                location_id="l1",
                quantity_change=-20,
                reference_type="outbound_order",
                reference_id=order_id,
                performed_at=datetime(2026, 3, 15, 14, i, tzinfo=UTC),
            )
        )

    # - Shipped 2 orders
    for order_id in ["ord-1", "ord-2"]:
        db.add(
            InventoryTransaction(
                tenant_id="t1",
                client_id="c1",
                transaction_type="ship",
                sku_id="s1",
                location_id="l1",
                quantity_change=-20,
                reference_type="outbound_order",
                reference_id=order_id,
                performed_at=datetime(2026, 3, 20, 16, 0, tzinfo=UTC),
            )
        )

    await db.flush()


@pytest.mark.asyncio
async def test_billing_calculation(db: AsyncSession):
    """Test that all charge types are correctly calculated."""
    await setup_billing_data(db)

    svc = BillingService(db, "t1")

    period = await svc.create_billing_period("c1", date(2026, 3, 1), date(2026, 3, 31))

    charges = await svc.calculate_charges(
        client_id="c1",
        period_id=period.id,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )

    charge_map = {c["charge_type"]: c for c in charges if "error" not in c}

    # Storage: 3 pallets × 30 days × $0.85 = $76.50
    assert "storage" in charge_map
    assert charge_map["storage"]["quantity"] == 90  # 3 × 30 pallet-days
    assert abs(charge_map["storage"]["total_amount"] - 76.50) < 0.01

    # Receiving: 200 units × $0.25 = $50.00
    assert "receiving" in charge_map
    assert charge_map["receiving"]["quantity"] == 200
    assert abs(charge_map["receiving"]["total_amount"] - 50.00) < 0.01

    # Pick lines: 3 lines × $0.50 = $1.50
    assert "pick" in charge_map
    assert charge_map["pick"]["quantity"] == 3

    # Pick orders: 2 orders × $2.00 = $4.00
    assert "pick_order" in charge_map
    assert charge_map["pick_order"]["quantity"] == 2

    # Shipping handling: 2 orders × $1.50 = $3.00
    assert "shipping_handling" in charge_map
    assert charge_map["shipping_handling"]["quantity"] == 2

    # Total = 76.50 + 50 + 1.50 + 4 + 3 = $135.00 (above $100 minimum)
    total = sum(c["total_amount"] for c in charges if "error" not in c)
    assert total > 100  # above minimum, no adjustment needed
    assert "minimum_adjustment" not in charge_map


@pytest.mark.asyncio
async def test_minimum_monthly_charge(db: AsyncSession):
    """Test that minimum monthly charge kicks in when activity is low."""
    tenant = Tenant(id="t2", name="Low Activity 3PL", code="LA", contact_email="la@test.com")
    db.add(tenant)
    client = Client(id="c2", tenant_id="t2", name="Quiet Client", code="QC")
    db.add(client)

    # Rate card with high minimum
    rc = RateCard(
        tenant_id="t2",
        client_id="c2",
        name="Minimum Heavy",
        effective_from=date(2026, 1, 1),
        rules={
            "storage_per_pallet_day": 0.50,
            "minimum_monthly": 500.00,
        },
    )
    db.add(rc)

    # Just 1 pallet
    inv = Inventory(
        tenant_id="t2",
        client_id="c2",
        warehouse_id="wh1",
        location_id="l1",
        sku_id="s1",
        quantity_on_hand=10,
    )
    db.add(inv)
    await db.flush()

    svc = BillingService(db, "t2")
    period = await svc.create_billing_period("c2", date(2026, 3, 1), date(2026, 3, 31))

    charges = await svc.calculate_charges(
        client_id="c2",
        period_id=period.id,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )

    charge_map = {c["charge_type"]: c for c in charges if "error" not in c}

    # Storage: 1 pallet × 30 days × $0.50 = $15.00 — way below $500 minimum
    assert "storage" in charge_map
    assert abs(charge_map["storage"]["total_amount"] - 15.00) < 0.01

    # Minimum adjustment should make up the difference: $500 - $15 = $485
    assert "minimum_adjustment" in charge_map
    assert abs(charge_map["minimum_adjustment"]["total_amount"] - 485.00) < 0.01


@pytest.mark.asyncio
async def test_expired_rate_card_is_not_selected(db: AsyncSession):
    tenant = Tenant(id="t-expired-rc", name="Expired Rate Tenant", code="ERT", contact_email="ert@test.com")
    client = Client(id="c-expired-rc", tenant_id=tenant.id, name="Expired Client", code="EC")
    db.add_all(
        [
            tenant,
            client,
            RateCard(
                tenant_id=tenant.id,
                client_id=client.id,
                name="Expired Rate",
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 3, 31),
                rules={"minimum_monthly": 500.00},
            ),
        ]
    )
    await db.flush()

    svc = BillingService(db, tenant.id)

    assert await svc.get_active_rate_card(client.id, date(2026, 4, 1)) is None


@pytest.mark.asyncio
async def test_invoice_generation(db: AsyncSession):
    """Test invoice generation from billing period."""
    await setup_billing_data(db)

    svc = BillingService(db, "t1")
    period = await svc.create_billing_period("c1", date(2026, 3, 1), date(2026, 3, 31))
    await svc.calculate_charges("c1", period.id, date(2026, 3, 1), date(2026, 3, 31))

    invoice = await svc.generate_invoice("c1", period.id, "INV-2026-03-001")

    assert invoice.invoice_number == "INV-2026-03-001"
    assert invoice.status == "draft"
    assert invoice.total_amount > 0
    assert invoice.currency == "USD"

    # Period should be marked as invoiced
    result = await db.execute(
        select(BillingLineItem).where(BillingLineItem.billing_period_id == period.id)
    )
    items = result.scalars().all()
    assert len(items) >= 4  # storage + receiving + pick + pick_order + shipping


@pytest.mark.asyncio
async def test_invoice_generation_uses_tax_and_terms_from_billing_profile(db: AsyncSession):
    """Invoice totals should reflect tax and payment term settings from billing profiles."""
    await setup_billing_data(db)

    tenant = (await db.execute(select(Tenant).where(Tenant.id == "t1"))).scalar_one()
    client = (await db.execute(select(Client).where(Client.id == "c1"))).scalar_one()
    tenant.settings = {
        "business_mode": "3pl",
        "billing_profile": {
            "legal_name": "Billing Test 3PL Ltd.",
            "tax_region": "eu",
            "tax_id": "TAX-123",
            "currency": "EUR",
            "payment_terms_days": 15,
            "payment_terms_label": "Net 15",
            "tax_rate_pct": 27,
            "tax_label": "VAT",
        },
    }
    client.settings = {
        "billing_profile": {
            "legal_name": "Billed Client Ltd.",
            "tax_region": "eu",
        }
    }
    await db.flush()

    svc = BillingService(db, "t1")
    period = await svc.create_billing_period("c1", date(2026, 3, 1), date(2026, 3, 31))
    await svc.calculate_charges("c1", period.id, date(2026, 3, 1), date(2026, 3, 31))

    invoice = await svc.generate_invoice("c1", period.id, "INV-2026-03-002")

    assert invoice.currency == "EUR"
    assert invoice.tax_amount == 36.45
    assert invoice.total_amount == 171.45
    assert invoice.due_date == invoice.issued_date + timedelta(days=15)


@pytest.mark.asyncio
async def test_invoice_generation_allows_us_profile_without_vat_registration(db: AsyncSession):
    await setup_billing_data(db)

    tenant = (await db.execute(select(Tenant).where(Tenant.id == "t1"))).scalar_one()
    client = (await db.execute(select(Client).where(Client.id == "c1"))).scalar_one()
    tenant.settings = {
        "business_mode": "3pl",
        "billing_profile": {
            "legal_name": "US Warehouse Services LLC",
            "tax_region": "us",
            "currency": "USD",
            "payment_terms_days": 10,
            "payment_terms_label": "Net 10",
            "tax_rate_pct": 8.25,
            "tax_label": "Sales Tax",
        },
    }
    client.settings = {
        "billing_profile": {
            "legal_name": "Acme US Retail LLC",
            "tax_region": "us",
        }
    }
    await db.flush()

    svc = BillingService(db, "t1")
    period = await svc.create_billing_period("c1", date(2026, 3, 1), date(2026, 3, 31))
    await svc.calculate_charges("c1", period.id, date(2026, 3, 1), date(2026, 3, 31))

    invoice = await svc.generate_invoice("c1", period.id, "INV-US-2026-03-001")

    assert invoice.currency == "USD"
    assert invoice.tax_amount == 11.14
    assert invoice.total_amount == 146.14
