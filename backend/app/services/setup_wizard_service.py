"""
Setup Wizard Service — guides new users through warehouse configuration
via a questionnaire flow. Answers auto-generate the full environment.

Flow:
  Step 1: Warehouse basics → creates Warehouse + Zones
  Step 2: Location scheme → auto-generates storage locations
  Step 3: First client → creates Client + portal user
  Step 4: Import SKUs → creates SKU records
  Step 5: Billing rules → creates Rate Card
  Step 6: Team members → creates operator accounts
  Step 7: Integrations → configures Shopify/Amazon

Each step is independent — user can skip or come back later.
Progress is saved so user can resume mid-setup.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.billing import RateCard
from app.models.client import Client
from app.models.inventory import SKU
from app.models.tenant import User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone


class SetupWizardService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def get_progress(self) -> dict:
        """Check which setup steps are completed."""
        warehouses = (
            await self.db.execute(
                select(func.count(Warehouse.id)).where(Warehouse.tenant_id == self.tenant_id)
            )
        ).scalar() or 0
        locations = (
            await self.db.execute(
                select(func.count(Location.id)).where(Location.tenant_id == self.tenant_id)
            )
        ).scalar() or 0
        clients = (
            await self.db.execute(
                select(func.count(Client.id)).where(Client.tenant_id == self.tenant_id)
            )
        ).scalar() or 0
        skus = (
            await self.db.execute(select(func.count(SKU.id)).where(SKU.tenant_id == self.tenant_id))
        ).scalar() or 0
        users = (
            await self.db.execute(
                select(func.count(User.id)).where(User.tenant_id == self.tenant_id)
            )
        ).scalar() or 0
        rate_cards = (
            await self.db.execute(
                select(func.count(RateCard.id)).where(RateCard.tenant_id == self.tenant_id)
            )
        ).scalar() or 0

        steps = [
            {
                "step": 1,
                "name": "warehouse",
                "title": "Set Up Your Warehouse",
                "done": warehouses > 0,
                "description": "Tell us about your warehouse facility — name, address, timezone.",
            },
            {
                "step": 2,
                "name": "locations",
                "title": "Create Storage Locations",
                "done": locations > 0,
                "description": "We'll auto-generate your location layout based on your shelf configuration.",
            },
            {
                "step": 3,
                "name": "client",
                "title": "Add Your First Client",
                "done": clients > 0,
                "description": "Who stores goods in your warehouse? Add their details and a portal login.",
            },
            {
                "step": 4,
                "name": "skus",
                "title": "Import Products (SKUs)",
                "done": skus > 0,
                "description": "Add the products you store. You can type them or upload a CSV later.",
            },
            {
                "step": 5,
                "name": "billing",
                "title": "Set Up Billing Rates",
                "done": rate_cards > 0,
                "description": "How do you charge your clients? Set storage, handling, and pick fees.",
            },
            {
                "step": 6,
                "name": "team",
                "title": "Invite Your Team",
                "done": users > 1,
                "description": "Add warehouse staff so they can log in and start picking.",
            },
        ]
        completed = sum(1 for s in steps if s["done"])
        return {
            "completed": completed,
            "total": len(steps),
            "progress_pct": round(completed / len(steps) * 100),
            "all_done": completed == len(steps),
            "steps": steps,
        }

    async def setup_warehouse(self, data: dict) -> dict:
        """Step 1: Create warehouse with basic info."""
        wh = Warehouse(
            tenant_id=self.tenant_id,
            name=data["name"],
            code=(data.get("code") or data["name"][:10].upper().replace(" ", "")),
            address=data.get("address"),
            timezone=data.get("timezone", "America/Chicago"),
        )
        self.db.add(wh)
        await self.db.flush()

        # Auto-create standard zones
        zones = [
            ("A", "Zone A — General Storage", False),
            ("B", "Zone B — High Value", False),
            ("S", "Staging — Receiving/Shipping Dock", False),
        ]
        zone_ids = {}
        for code, name, is_agv in zones:
            z = Zone(
                tenant_id=self.tenant_id,
                warehouse_id=wh.id,
                name=name,
                code=code,
                is_agv_zone=is_agv,
            )
            self.db.add(z)
            await self.db.flush()
            zone_ids[code] = z.id

        # Create dock location
        self.db.add(
            Location(
                tenant_id=self.tenant_id,
                warehouse_id=wh.id,
                zone_id=zone_ids["S"],
                barcode="DOCK-01",
                aisle="D",
                rack="01",
                level="01",
                position="01",
                location_type=LocationType.STAGING.value,
                current_status=LocationStatus.AVAILABLE.value,
                pick_sequence=0,
            )
        )

        await self.db.flush()
        return {
            "warehouse_id": wh.id,
            "name": wh.name,
            "zones_created": len(zones),
            "dock_location": "DOCK-01",
        }

    async def setup_locations(self, data: dict) -> dict:
        """
        Step 2: Auto-generate storage locations based on warehouse dimensions.

        data: {
            "warehouse_id": "...",
            "aisles": 3,           # number of aisles
            "racks_per_aisle": 5,  # racks per aisle
            "levels": 3,           # vertical levels
            "agv_accessible": false
        }
        """
        wh_id = data["warehouse_id"]
        aisles = data.get("aisles", 3)
        racks = data.get("racks_per_aisle", 4)
        levels = data.get("levels", 3)
        positions_per_level = data.get("positions_per_level", 5)
        agv = data.get("agv_accessible", False)
        aisle_width_m = float(data.get("aisle_width_m", 3.2))
        level_height_m = float(data.get("level_height_m", 1.5))
        level_capacity_kg = float(data.get("level_capacity_kg", 1200.0))
        raw_level_profiles = data.get("level_profiles") or []
        level_profiles = []
        for index in range(levels):
            profile = raw_level_profiles[index] if index < len(raw_level_profiles) else {}
            level_profiles.append(
                {
                    "level": index + 1,
                    "height_m": float(profile.get("height_m", level_height_m)),
                    "capacity_kg": float(profile.get("capacity_kg", level_capacity_kg)),
                    "positions_count": int(profile.get("positions_count", positions_per_level)),
                }
            )
        total_rack_height_m = round(sum(profile["height_m"] for profile in level_profiles), 2)
        min_level_capacity_kg = (
            min(profile["capacity_kg"] for profile in level_profiles)
            if level_profiles
            else level_capacity_kg
        )
        total_positions_per_rack = sum(profile["positions_count"] for profile in level_profiles)

        # Find zone A
        zone_result = await self.db.execute(
            select(Zone.id).where(
                Zone.warehouse_id == wh_id,
                Zone.code == "A",
            )
        )
        zone_id = zone_result.scalar()
        if not zone_id:
            return {"error": "Zone A not found. Run warehouse setup first."}

        warehouse_result = await self.db.execute(
            select(Warehouse).where(
                Warehouse.id == wh_id,
                Warehouse.tenant_id == self.tenant_id,
            )
        )
        warehouse = warehouse_result.scalar_one_or_none()
        if warehouse:
            address = dict(warehouse.address or {})
            existing_rules = dict(address.get("_planner_rules", {}))
            address["_planner_rules"] = {
                **existing_rules,
                "rack_height_m": total_rack_height_m,
                "beam_capacity_kg": min_level_capacity_kg,
                "aisle_width_m": aisle_width_m,
                "agv_turning_radius_m": float(existing_rules.get("agv_turning_radius_m", 1.8)),
                "level_profiles": level_profiles,
                "positions_per_level": positions_per_level,
            }
            warehouse.address = address

        created = 0
        for a in range(1, aisles + 1):
            for r in range(1, racks + 1):
                for level in range(1, levels + 1):
                    level_profile = level_profiles[level - 1]
                    positions = max(
                        int(level_profile.get("positions_count", positions_per_level)), 1
                    )
                    for p in range(1, positions + 1):
                        loc = Location(
                            tenant_id=self.tenant_id,
                            warehouse_id=wh_id,
                            zone_id=zone_id,
                            barcode=f"A-{a:02d}-{r:02d}-{level:02d}-{p:02d}",
                            aisle=f"{a:02d}",
                            rack=f"{r:02d}",
                            level=f"{level:02d}",
                            position=f"{p:02d}",
                            location_type=LocationType.STORAGE.value,
                            current_status=LocationStatus.AVAILABLE.value,
                            coordinate_x=float(a * 3) if agv else None,
                            coordinate_y=float(r * 2) if agv else None,
                            coordinate_z=float(level * 1.5) if agv else None,
                            is_agv_accessible=agv,
                            pick_sequence=a * 10000 + r * 1000 + level * 100 + p,
                        )
                        self.db.add(loc)
                        created += 1

        await self.db.flush()
        return {
            "locations_created": created,
            "layout": f"{aisles} aisles × {racks} racks × {levels} levels × {total_positions_per_rack} positions per rack",
            "agv_accessible": agv,
            "barcode_format": "A-{aisle}-{rack}-{level}-{position}",
            "planner_profile": {
                "aisle_width_m": aisle_width_m,
                "level_height_m": level_height_m,
                "level_capacity_kg": level_capacity_kg,
                "rack_height_m": total_rack_height_m,
                "level_profiles": level_profiles,
                "positions_per_level": positions_per_level,
            },
        }

    async def setup_first_client(self, data: dict) -> dict:
        """Step 3: Create first client with optional portal user."""
        client = Client(
            tenant_id=self.tenant_id,
            name=data["name"],
            code=data.get("code", data["name"][:6].upper().replace(" ", "")),
            contact_email=data.get("email"),
            billing_enabled=True,
            portal_access=True,
        )
        self.db.add(client)
        await self.db.flush()

        result = {"client_id": client.id, "name": client.name}

        # Create portal user if email+password provided
        if data.get("portal_email") and data.get("portal_password"):
            user = User(
                tenant_id=self.tenant_id,
                email=data["portal_email"],
                hashed_password=hash_password(data["portal_password"]),
                full_name=data.get("portal_name", data["name"]),
                role="client_viewer",
                client_id=client.id,
            )
            self.db.add(user)
            result["portal_user"] = data["portal_email"]

        await self.db.flush()
        return result

    async def setup_skus(self, data: dict) -> dict:
        """Step 4: Add SKUs for a client."""
        client_id = data["client_id"]
        skus = data.get("skus", [])
        created = 0

        for s in skus:
            sku = SKU(
                tenant_id=self.tenant_id,
                client_id=client_id,
                sku_code=s["sku_code"],
                name=s["name"],
                barcode=s.get("barcode"),
                weight_kg=s.get("weight_kg"),
            )
            self.db.add(sku)
            created += 1

        await self.db.flush()
        return {"skus_created": created, "client_id": client_id}

    async def setup_billing(self, data: dict) -> dict:
        """Step 5: Create rate card for a client."""
        rc = RateCard(
            tenant_id=self.tenant_id,
            client_id=data["client_id"],
            name=f"{data.get('client_name', 'Client')} Rate Card",
            effective_from=date.today(),
            rules={
                "storage_per_pallet_day": data.get("storage_rate", 0.85),
                "receiving_per_unit": data.get("receiving_rate", 0.25),
                "pick_per_order": data.get("pick_per_order", 2.00),
                "pick_per_line": data.get("pick_per_line", 0.50),
                "shipping_handling_per_order": data.get("shipping_rate", 1.50),
                "minimum_monthly": data.get("minimum_monthly", 200),
            },
        )
        self.db.add(rc)
        await self.db.flush()
        return {"rate_card_id": rc.id, "rules": rc.rules}

    async def setup_team(self, data: dict) -> dict:
        """Step 6: Add team members."""
        members = data.get("members", [])
        created = []

        for m in members:
            user = User(
                tenant_id=self.tenant_id,
                email=m["email"],
                hashed_password=hash_password(
                    m["password"]
                ),  # password required, validated by hash_password
                full_name=m["name"],
                role=m.get("role", "operator"),
            )
            self.db.add(user)
            created.append({"email": m["email"], "name": m["name"], "role": user.role})

        await self.db.flush()
        return {"team_members_created": len(created), "members": created}

    async def quick_setup(self, data: dict) -> dict:
        """
        Express setup — answer all questions at once, system builds everything.
        For users who want to get started immediately.
        """
        results = {"steps_completed": []}

        # 1. Warehouse
        wh = await self.setup_warehouse(
            {
                "name": data.get("warehouse_name", "My Warehouse"),
                "address": data.get("warehouse_address"),
                "timezone": data.get("timezone", "America/Chicago"),
            }
        )
        results["steps_completed"].append("warehouse")
        results["warehouse"] = wh

        # 2. Locations
        locs = await self.setup_locations(
            {
                "warehouse_id": wh["warehouse_id"],
                "aisles": data.get("aisles", 3),
                "racks_per_aisle": data.get("racks_per_aisle", 4),
                "levels": data.get("levels", 3),
                "positions_per_level": data.get("positions_per_level", 5),
                "agv_accessible": data.get("agv_accessible", False),
                "aisle_width_m": data.get("aisle_width_m", 3.2),
                "level_height_m": data.get("level_height_m", 1.5),
                "level_capacity_kg": data.get("level_capacity_kg", 1200.0),
                "level_profiles": data.get("level_profiles"),
            }
        )
        results["steps_completed"].append("locations")
        results["locations"] = locs

        # 3. First client
        if data.get("client_name"):
            client = await self.setup_first_client(
                {
                    "name": data["client_name"],
                    "email": data.get("client_email"),
                    "portal_email": data.get("client_portal_email"),
                    "portal_password": data.get("client_portal_password"),
                }
            )
            results["steps_completed"].append("client")
            results["client"] = client

            # 4. SKUs
            if data.get("skus"):
                sku_result = await self.setup_skus(
                    {
                        "client_id": client["client_id"],
                        "skus": data["skus"],
                    }
                )
                results["steps_completed"].append("skus")
                results["skus"] = sku_result

            # 5. Billing
            if data.get("storage_rate") or data.get("minimum_monthly"):
                billing = await self.setup_billing(
                    {
                        "client_id": client["client_id"],
                        "client_name": data["client_name"],
                        "storage_rate": data.get("storage_rate", 0.85),
                        "receiving_rate": data.get("receiving_rate", 0.25),
                        "pick_per_order": data.get("pick_per_order", 2.00),
                        "pick_per_line": data.get("pick_per_line", 0.50),
                        "minimum_monthly": data.get("minimum_monthly", 200),
                    }
                )
                results["steps_completed"].append("billing")
                results["billing"] = billing

        # 6. Team
        if data.get("team_members"):
            team = await self.setup_team({"members": data["team_members"]})
            results["steps_completed"].append("team")
            results["team"] = team

        results["setup_complete"] = True
        results["message"] = (
            f"Your warehouse is ready! {locs['locations_created']} locations created."
        )
        return results
