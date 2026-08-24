"""Validate the Dallas local-agent blueprint draft through backend preview/WCS gates.

This script is intentionally validate-only. It does not call the warehouse
blueprint confirm endpoint and does not import WCS point mappings. A transient
in-memory SQLite database is used only so the WCS mapping validator can match
draft storage point codes to WMS Location rows.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.agent import AgentToolRunRequest, run_agent_tool
from app.api.v1.endpoints.integrations import (
    WcsPointMapping,
    WcsPointMappingImportRequest,
    WcsPointMappingRequest,
    import_wcs_point_mappings,
    validate_wcs_point_mappings,
)
from app.core.database import Base
from app.core.security import TokenPayload, UserRole
from app.models import *  # noqa: F401,F403 - register all models for metadata
from app.models.tenant import Tenant
from app.models.warehouse import Location, LocationStatus, Warehouse, Zone


REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_PATH = REPO_ROOT / "exports" / "dallas-local-agent-blueprint-draft.json"
SUMMARY_PATH = REPO_ROOT / "exports" / "dallas-backend-wcs-validate-only-summary.json"


def assert_condition(condition: bool, message: str, details: Any | None = None) -> None:
    if not condition:
        if details is None:
            raise AssertionError(message)
        raise AssertionError(f"{message}: {details}")


def role_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("point_role") or row.get("point_type")) for row in rows))


def point_codes(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("point_code")) for row in rows if row.get("point_code")}


def assert_point_codes_match(local_rows: list[dict[str, Any]], backend_rows: list[dict[str, Any]]) -> None:
    local_codes = point_codes(local_rows)
    backend_codes = point_codes(backend_rows)
    missing_from_backend = sorted(local_codes - backend_codes)
    extra_from_backend = sorted(backend_codes - local_codes)
    assert_condition(
        not missing_from_backend and not extra_from_backend,
        "Local-agent and backend WCS point-code sets differ",
        {
            "missing_from_backend": missing_from_backend[:10],
            "extra_from_backend": extra_from_backend[:10],
        },
    )


async def materialize_preview_locations(
    db,
    tenant_id: str,
    preview: dict[str, Any],
) -> Warehouse:
    """Create transient WMS locations from preview output for WCS validation only."""
    warehouse = Warehouse(
        tenant_id=tenant_id,
        name=preview["target"]["name"],
        code=preview["target"]["code"],
        timezone=preview["target"].get("timezone") or "America/Chicago",
        address={},
    )
    db.add(warehouse)
    await db.flush()

    for zone_payload in preview["zones"]:
        if not zone_payload.get("create_locations"):
            continue
        zone = Zone(
            tenant_id=tenant_id,
            warehouse_id=warehouse.id,
            name=zone_payload["name"],
            code=zone_payload["code"],
            sequence=int(zone_payload.get("sequence") or 0),
            is_agv_zone=True,
            zone_type=zone_payload["type"],
            coordinate_x=(zone_payload.get("layout_percent") or {}).get("x"),
            coordinate_y=(zone_payload.get("layout_percent") or {}).get("y"),
            coordinate_z=None,
            dimensions=zone_payload.get("dimensions") or {},
            layout_metadata={
                "coordinate_system": "drawing_percent",
                "layout_percent": zone_payload.get("layout_percent") or {},
                "planning_standard": "docs/36-agv-planning-standard.md",
            },
            drawing_source={"source_type": "validate_only"},
        )
        db.add(zone)
        await db.flush()
        for location_payload in zone_payload["locations"]:
            layout_percent = location_payload.get("layout_percent") or {}
            db.add(
                Location(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse.id,
                    zone_id=zone.id,
                    barcode=location_payload["barcode"],
                    aisle=location_payload["aisle"],
                    rack=location_payload["rack"],
                    level=location_payload["level"],
                    position=location_payload["position"],
                    coordinate_x=layout_percent.get("x"),
                    coordinate_y=layout_percent.get("y"),
                    coordinate_z=None,
                    is_agv_accessible=True,
                    location_type=location_payload["location_type"],
                    current_status=LocationStatus.AVAILABLE.value,
                    pick_sequence=int(location_payload.get("pick_sequence") or 0),
                    dimensions=location_payload.get("dimensions") or {},
                    layout_metadata={
                        "coordinate_system": "drawing_percent",
                        "layout_percent": layout_percent,
                        "slot_layout_percent": location_payload.get("slot_layout_percent") or {},
                    },
                    drawing_source={"source_type": "validate_only", "zone_code": zone_payload["code"]},
                    wcs_point_metadata={},
                )
            )
    await db.flush()
    return warehouse


async def main() -> None:
    assert_condition(
        BLUEPRINT_PATH.exists(),
        f"Missing {BLUEPRINT_PATH}. Run `node wms-agent/scripts/verify-dallas-blueprint-flow.mjs` first.",
    )
    payload = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    local_mappings = payload.get("wcs_point_mapping_draft") or []
    assert_condition(payload.get("warehouse", {}).get("code") == "DAL", "Local blueprint warehouse code must be DAL")
    assert_condition(len(local_mappings) == 119, "Local blueprint should contain 119 WCS draft points")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        tenant_id = "dallas-validate-only-tenant"
        tenant = Tenant(
            id=tenant_id,
            name="Dallas Validate Only Tenant",
            code="DVO",
            contact_email="ops@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": ["warehouse.blueprint.preview"],
                }
            },
        )
        db.add(tenant)
        await db.flush()
        current_user = TokenPayload(
            sub="tenant-admin",
            tenant_id=tenant_id,
            client_id=None,
            role=UserRole.TENANT_ADMIN,
            permissions=["master_data.manage"],
            exp=datetime.now(UTC),
        )

        preview_response = await run_agent_tool(
            AgentToolRunRequest(tool_name="warehouse.blueprint.preview", args=payload),
            current_user=current_user,
            db=db,
        )
        preview = preview_response.result
        backend_mappings = preview["wcs_point_mapping_draft"]
        assert_condition(preview["ok"] is True, "Backend blueprint preview must be ok", preview.get("blocking_errors"))
        assert_condition(preview["dry_run"] is True and preview["writes"] is False, "Backend preview must remain dry-run")
        assert_condition(preview["confirmation_required_for_write"] is True, "Backend preview must require confirmation for writes")
        assert_condition(preview["summary"]["zone_count"] == 9, "Backend preview zone count mismatch")
        assert_condition(preview["summary"]["location_count"] == 108, "Backend preview location count mismatch")
        assert_condition(preview["summary"]["will_create_zones"] == 4, "Backend preview storage-zone count mismatch")
        assert_condition(preview["summary"]["dock_door_count"] == 8, "Backend preview dock-door count mismatch")
        assert_condition(preview["summary"]["wcs_point_mapping_draft_count"] == 119, "Backend WCS draft count mismatch")
        assert_condition(all(check["ok"] for check in preview["validation"]), "Backend AGV validation checks failed", preview["validation"])
        assert_point_codes_match(local_mappings, backend_mappings)
        assert_condition(
            role_counts(backend_mappings) == {"storage": 108, "dock": 8, "buffer": 2, "agv_station": 1},
            "Backend WCS point role counts mismatch",
            role_counts(backend_mappings),
        )

        warehouse = await materialize_preview_locations(db, tenant_id, preview)
        mapping_models = [WcsPointMapping(**row) for row in backend_mappings]
        validation = await validate_wcs_point_mappings(
            body=WcsPointMappingRequest(warehouse_id=warehouse.id, mappings=mapping_models),
            current_user=current_user,
            db=db,
        )
        validate_only_import = await import_wcs_point_mappings(
            body=WcsPointMappingImportRequest(
                warehouse_id=warehouse.id,
                mappings=mapping_models,
                validate_only=True,
            ),
            current_user=current_user,
            db=db,
        )
        assert_condition(validation["ok"] is True, "WCS point-mapping validation must pass", validation["issues"])
        assert_condition(validate_only_import["ok"] is True, "WCS validate-only import path must pass", validate_only_import["issues"])
        assert_condition(validation["summary"] == validate_only_import["summary"], "Validate and validate-only import summaries differ")
        assert_condition(validation["summary"]["rows"] == 119, "WCS validation row count mismatch")
        assert_condition(validation["summary"]["mapped_locations"] == 108, "WCS mapped location count mismatch")
        assert_condition(validation["summary"]["external_points"] == 11, "WCS external point count mismatch")
        assert_condition(validation["summary"]["unmapped_agv_accessible_locations"] == 0, "All AGV locations should be mapped")
        assert_condition(not (warehouse.address or {}).get("_wcs", {}).get("point_mappings"), "Validate-only import must not write WCS mappings")

        summary = {
            "ok": True,
            "source_blueprint": str(BLUEPRINT_PATH),
            "backend_preview": {
                "warehouse": preview["target"],
                "summary": preview["summary"],
                "role_counts": role_counts(backend_mappings),
                "confirmation_required_for_write": preview["confirmation_required_for_write"],
                "writes": preview["writes"],
                "blocking_errors": preview["blocking_errors"],
            },
            "local_vs_backend": {
                "point_code_sets_equal": True,
                "local_point_count": len(local_mappings),
                "backend_point_count": len(backend_mappings),
                "first_point_code": backend_mappings[0]["point_code"],
            },
            "wcs_validate": validation["summary"],
            "validate_only_import": {
                "ok": validate_only_import["ok"],
                "summary": validate_only_import["summary"],
                "writes": False,
            },
            "writes_executed": {
                "warehouse_blueprint_confirm": False,
                "wcs_point_mapping_import": False,
            },
        }
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
