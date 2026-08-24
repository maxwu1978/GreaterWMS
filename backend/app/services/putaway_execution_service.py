from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import HandlingUnit
from app.models.warehouse import Location, LocationType, Warehouse


@dataclass(slots=True)
class PutawayExecutionDecision:
    mode: str
    agv_eligible: bool
    reason: str


class PutawayExecutionService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def decide(
        self,
        warehouse_id: str,
        source_location_id: str | None = None,
        handling_unit_id: str | None = None,
    ) -> PutawayExecutionDecision:
        source_location = None
        if source_location_id:
            source_location = await self.db.scalar(
                select(Location).where(
                    Location.id == source_location_id,
                    Location.tenant_id == self.tenant_id,
                )
            )

        handling_unit = None
        if handling_unit_id:
            handling_unit = await self.db.scalar(
                select(HandlingUnit).where(
                    HandlingUnit.id == handling_unit_id,
                    HandlingUnit.tenant_id == self.tenant_id,
                )
            )

        warehouse = await self.db.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == self.tenant_id,
            )
        )
        planner_rules = (
            dict((warehouse.address or {}).get("_planner_rules", {}))
            if warehouse and warehouse.address
            else {}
        )
        agv_payload_limit = float(planner_rules.get("agv_max_payload_kg", 30.0))

        has_agv_storage = await self.db.scalar(
            select(Location.id)
            .where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
                Location.location_type == LocationType.STORAGE.value,
                Location.is_agv_accessible == True,  # noqa: E712
            )
            .limit(1)
        )

        measured_weight = (
            float(handling_unit.measured_weight_kg)
            if handling_unit and handling_unit.measured_weight_kg is not None
            else None
        )
        overweight = bool(measured_weight is not None and measured_weight > agv_payload_limit)
        source_agv_ready = bool(source_location and source_location.is_agv_accessible)

        if not has_agv_storage:
            return PutawayExecutionDecision(
                mode="human",
                agv_eligible=False,
                reason="no_agv_storage_available",
            )

        if overweight:
            return PutawayExecutionDecision(
                mode="human",
                agv_eligible=False,
                reason="unit_exceeds_agv_payload",
            )

        if source_agv_ready:
            return PutawayExecutionDecision(
                mode="agv",
                agv_eligible=True,
                reason="agv_ready_from_staging",
            )

        return PutawayExecutionDecision(
            mode="hybrid",
            agv_eligible=True,
            reason="human_to_agv_handoff_required",
        )
