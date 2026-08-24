"""
Seed script — creates database tables and populates test data.
Run: python seed.py
"""

import asyncio
from datetime import UTC, datetime, date

from app.core.database import Base, engine, async_session_factory
from app.core.security import hash_password, UserRole
from app.models import *  # noqa — register all models


async def seed():
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")

    async with async_session_factory() as db:
        # ─── Tenant ───
        tenant = Tenant(
            id="tenant-001",
            name="DFW Logistics LLC",
            code="DFW",
            contact_email="admin@dfwlogistics.com",
            contact_phone="(214) 555-0100",
            address={"street": "2806 Green Circle Dr.", "city": "Mansfield", "state": "TX", "zip": "76063", "country": "US"},
            plan_tier="growth",
        )
        db.add(tenant)

        # ─── Users ───
        admin_user = User(
            id="user-admin",
            tenant_id="tenant-001",
            email="admin@dfwlogistics.com",
            hashed_password=hash_password("admin123"),
            full_name="Max Admin",
            role=UserRole.TENANT_ADMIN.value,
        )
        db.add(admin_user)

        operator_user = User(
            id="user-operator",
            tenant_id="tenant-001",
            email="operator@dfwlogistics.com",
            hashed_password=hash_password("oper123"),
            full_name="John Operator",
            role=UserRole.OPERATOR.value,
        )
        db.add(operator_user)

        # ─── Clients (cargo owners) ───
        client_acme = Client(
            id="client-acme",
            tenant_id="tenant-001",
            name="Acme Pet Supplies",
            code="ACME",
            contact_email="logistics@acmepets.com",
        )
        db.add(client_acme)

        client_beta = Client(
            id="client-beta",
            tenant_id="tenant-001",
            name="Beta Electronics",
            code="BETA",
            contact_email="warehouse@betaelec.com",
        )
        db.add(client_beta)

        # Client portal user
        client_user = User(
            id="user-client",
            tenant_id="tenant-001",
            email="logistics@acmepets.com",
            hashed_password=hash_password("client123"),
            full_name="Sarah Client",
            role=UserRole.CLIENT_VIEWER.value,
            client_id="client-acme",
        )
        db.add(client_user)

        # ─── Warehouse ───
        warehouse = Warehouse(
            id="wh-dfw1",
            tenant_id="tenant-001",
            name="DFW Warehouse #1",
            code="DFW1",
            address={"street": "2806 Green Circle Dr.", "city": "Mansfield", "state": "TX", "zip": "76063"},
            timezone="America/Chicago",
        )
        db.add(warehouse)

        # ─── Zones ───
        zone_a = Zone(id="zone-a", tenant_id="tenant-001", warehouse_id="wh-dfw1", name="Zone A — Ambient", code="A")
        zone_b = Zone(id="zone-b", tenant_id="tenant-001", warehouse_id="wh-dfw1", name="Zone B — High Value", code="B")
        zone_stage = Zone(id="zone-stage", tenant_id="tenant-001", warehouse_id="wh-dfw1", name="Staging Area", code="S")
        db.add_all([zone_a, zone_b, zone_stage])

        # ─── Locations ───
        # Staging dock
        db.add(Location(
            id="loc-dock-1", tenant_id="tenant-001", warehouse_id="wh-dfw1", zone_id="zone-stage",
            barcode="DOCK-01", aisle="D", rack="01", level="01", position="01",
            location_type="staging", current_status="available",
        ))

        # Storage locations in Zone A (AGV accessible)
        for aisle in range(1, 4):
            for rack in range(1, 5):
                for level in range(1, 4):
                    loc_id = f"loc-A-{aisle:02d}-{rack:02d}-{level:02d}"
                    db.add(Location(
                        id=loc_id, tenant_id="tenant-001", warehouse_id="wh-dfw1", zone_id="zone-a",
                        barcode=f"A-{aisle:02d}-{rack:02d}-{level:02d}-01",
                        aisle=f"{aisle:02d}", rack=f"{rack:02d}", level=f"{level:02d}", position="01",
                        location_type="storage", current_status="available",
                        coordinate_x=float(aisle * 3), coordinate_y=float(rack * 2), coordinate_z=float(level * 1.5),
                        is_agv_accessible=True,
                        pick_sequence=aisle * 100 + rack * 10 + level,
                    ))

        # ─── SKUs ───
        skus_data = [
            ("sku-dog-food", "client-acme", "DOG-FOOD-25LB", "Premium Dog Food 25lb", "012345678901", 11.3),
            ("sku-cat-toy", "client-acme", "CAT-TOY-MOUSE", "Interactive Cat Toy Mouse", "012345678902", 0.15),
            ("sku-leash", "client-acme", "LEASH-RETRACT", "Retractable Dog Leash 16ft", "012345678903", 0.4),
            ("sku-bowl", "client-acme", "BOWL-STEEL-L", "Stainless Steel Bowl Large", "012345678904", 0.6),
            ("sku-usb-cable", "client-beta", "USB-C-6FT", "USB-C Cable 6ft", "098765432101", 0.05),
            ("sku-phone-case", "client-beta", "CASE-IP15-BLK", "iPhone 15 Case Black", "098765432102", 0.08),
        ]
        for sid, cid, code, name, barcode, weight in skus_data:
            db.add(SKU(
                id=sid, tenant_id="tenant-001", client_id=cid,
                sku_code=code, name=name, barcode=barcode, weight_kg=weight,
            ))

        # ─── Pre-existing Inventory ───
        inventory_data = [
            ("client-acme", "sku-dog-food", "loc-A-01-01-01", 120),
            ("client-acme", "sku-cat-toy", "loc-A-01-02-01", 500),
            ("client-acme", "sku-leash", "loc-A-01-03-01", 200),
            ("client-acme", "sku-bowl", "loc-A-02-01-01", 80),
            ("client-beta", "sku-usb-cable", "loc-A-02-02-01", 1000),
            ("client-beta", "sku-phone-case", "loc-A-02-03-01", 300),
        ]
        for cid, sid, lid, qty in inventory_data:
            loc = lid  # update location status
            db.add(Inventory(
                tenant_id="tenant-001", client_id=cid, warehouse_id="wh-dfw1",
                location_id=lid, sku_id=sid,
                quantity_on_hand=qty, received_at=datetime.now(UTC),
            ))

        # ─── Inbound Order (ready to receive) ───
        inbound = InboundOrder(
            id="inb-001", tenant_id="tenant-001", client_id="client-acme", warehouse_id="wh-dfw1",
            order_number="PO-2026-0042", reference_number="ACME-PO-1234",
            status="expected", supplier_name="PetSupply Wholesale Inc.",
            expected_date=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
        )
        db.add(inbound)
        db.add(InboundOrderLine(
            id="inb-001-line-1", tenant_id="tenant-001", order_id="inb-001",
            sku_id="sku-dog-food", quantity_expected=200,
        ))
        db.add(InboundOrderLine(
            id="inb-001-line-2", tenant_id="tenant-001", order_id="inb-001",
            sku_id="sku-cat-toy", quantity_expected=500,
        ))

        # ─── Outbound Orders ───
        out1 = OutboundOrder(
            id="out-001", tenant_id="tenant-001", client_id="client-acme", warehouse_id="wh-dfw1",
            order_number="SO-2026-0108", reference_number="SHOP-5001",
            status="pending", priority=3, channel="shopify",
            ship_to_name="Emily Johnson",
            ship_to_address={"street": "742 Evergreen Terrace", "city": "Dallas", "state": "TX", "zip": "75201"},
        )
        db.add(out1)
        db.add(OutboundOrderLine(
            id="out-001-line-1", tenant_id="tenant-001", order_id="out-001",
            sku_id="sku-dog-food", quantity_ordered=2,
        ))
        db.add(OutboundOrderLine(
            id="out-001-line-2", tenant_id="tenant-001", order_id="out-001",
            sku_id="sku-leash", quantity_ordered=1,
        ))

        out2 = OutboundOrder(
            id="out-002", tenant_id="tenant-001", client_id="client-beta", warehouse_id="wh-dfw1",
            order_number="SO-2026-0109", reference_number="AMZ-9002",
            status="pending", priority=5, channel="amazon",
            ship_to_name="Michael Chen",
            ship_to_address={"street": "123 Main St", "city": "Plano", "state": "TX", "zip": "75024"},
        )
        db.add(out2)
        db.add(OutboundOrderLine(
            id="out-002-line-1", tenant_id="tenant-001", order_id="out-002",
            sku_id="sku-usb-cable", quantity_ordered=5,
        ))

        # ─── Plan Tiers ───
        from datetime import timedelta
        plan_starter = PlanTier(
            id="plan-starter", name="Starter", code="starter",
            price_monthly=149, price_yearly=1490,
            max_clients=5, max_skus=1000, max_orders_per_day=200,
            max_users=5, max_warehouses=1, trial_days=14, sort_order=1,
            features={"shopify": False, "amazon": False, "agv": False, "portal": True, "api_full": False},
        )
        plan_growth = PlanTier(
            id="plan-growth", name="Growth", code="growth",
            price_monthly=399, price_yearly=3990,
            max_clients=20, max_skus=10000, max_orders_per_day=2000,
            max_users=20, max_warehouses=3, trial_days=14, sort_order=2,
            features={"shopify": True, "amazon": True, "agv": False, "portal": True, "api_full": True},
        )
        plan_enterprise = PlanTier(
            id="plan-enterprise", name="Enterprise", code="enterprise",
            price_monthly=899, price_yearly=8990,
            max_clients=999999, max_skus=999999, max_orders_per_day=999999,
            max_users=999999, max_warehouses=999999, trial_days=30, sort_order=3,
            features={"shopify": True, "amazon": True, "agv": True, "portal": True, "api_full": True},
        )
        db.add_all([plan_starter, plan_growth, plan_enterprise])

        # ─── Subscription for test tenant (active trial) ───
        db.add(Subscription(
            tenant_id="tenant-001", plan_id="plan-growth",
            status="active",
            current_period_start=date.today(),
            current_period_end=date.today() + timedelta(days=30),
            trial_end_date=date.today() + timedelta(days=14),
        ))

        # ─── Rate Card ───
        db.add(RateCard(
            tenant_id="tenant-001", client_id="client-acme", name="Acme Standard Rate",
            effective_from=date(2026, 1, 1),
            rules={
                "storage_per_pallet_day": 0.85,
                "receiving_per_unit": 0.25,
                "pick_per_order": 2.00,
                "pick_per_line": 0.50,
                "shipping_handling_per_order": 1.50,
                "minimum_monthly": 200.00,
            },
        ))

        await db.commit()
        print("Seed data inserted.")

    print()
    print("=== Test Accounts ===")
    print("Operator:  admin@dfwlogistics.com / admin123")
    print("Picker:    operator@dfwlogistics.com / oper123")
    print("Client:    logistics@acmepets.com / client123")
    print()
    print("=== Ready! Run: uvicorn app.main:app --reload ===")


if __name__ == "__main__":
    asyncio.run(seed())
