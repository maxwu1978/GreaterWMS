"""Regression tests: agent console (split from tests/test_regressions.py)."""

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.agent import (
    DEFAULT_ALLOWED_TOOLS,
    DIRECT_IMPORT_WRITE_TOOLS,
    AgentTeamRunRequest,
    AgentToolRunRequest,
    SettingsAgentRequest,
    WarehouseBlueprintAgentRequest,
    agent_team_status,
    confirm_settings_change_for_agent,
    confirm_warehouse_blueprint_for_agent,
    run_agent_team,
    run_agent_tool,
)
from app.api.v1.endpoints.integrations import (
    WcsPointMapping,
    WcsPointMappingRequest,
    validate_wcs_point_mappings,
)
from app.core.security import TokenPayload, UserRole
from app.models.billing import RateCard
from app.models.client import Client
from app.models.inventory import SKU, Inventory
from app.models.tenant import Tenant, User
from app.models.warehouse import Location, LocationStatus, LocationType, Warehouse, Zone
from app.services.agent_team_service import AgentTeamService


@pytest.mark.asyncio
async def test_agent_settings_get_returns_safe_provider_metadata(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Agent Settings Tenant",
            code="AST",
            contact_email="ops@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "provider_type": "qwen",
                    "provider_label": "Qwen Ops",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "model_name": "qwen-max",
                    "api_key": "qwen-secret",
                    "allowed_tools": ["settings.agent.get"],
                    "requires_human_confirmation_for_writes": True,
                }
            },
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["users.manage"],
        exp=datetime.now(UTC),
    )

    response = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.agent.get", args={}),
        current_user=current_user,
        db=db,
    )

    assert response.tool_name == "settings.agent.get"
    assert response.result["provider_type"] == "qwen"
    assert response.result["provider_label"] == "Qwen Ops"
    assert response.result["model_name"] == "qwen-max"
    assert response.result["has_api_key"] is True
    assert response.result["allowed_tools"] == ["settings.agent.get"]
    assert "qwen-secret" not in str(response.result)
    assert "api_key" not in response.result


@pytest.mark.asyncio
async def test_agent_phase_a_settings_tools_return_safe_configuration(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    allowed_tools = [
        "settings.receiving_codes.get",
        "settings.receiving_labels.get",
        "settings.users.list",
        "settings.users.get",
        "settings.permissions.explain",
        "settings.client_profile.get",
        "settings.billing.explain",
        "settings.warehouse_locations.list",
        "settings.warehouse.get",
        "settings.rate_card.get",
        "settings.receiving_codes.preview",
        "settings.receiving_labels.preview",
        "settings.client_profile.preview",
        "settings.sku.preview",
        "settings.warehouse_location.preview",
        "settings.billing_rate_card.preview",
    ]
    db.add(
        Tenant(
            id=tenant_id,
            name="Phase A Tenant",
            code="PAT",
            contact_email="ops@example.com",
            settings={
                "business_mode": "3pl",
                "billing_profile": {"legal_name": "Phase A 3PL", "api_key": "tenant-secret"},
                "receiving_code_rules": {
                    "prefix": "BOX",
                    "separator": "-",
                    "include_order_number": False,
                    "sequence_padding": 4,
                    "uppercase": True,
                },
                "receiving_label_template": {
                    "fields": ["order_number", "sku_code", "customer_barcode"],
                    "show_field_labels": False,
                },
                "agent_console": {"enabled": True, "allowed_tools": allowed_tools},
            },
        )
    )
    db.add(
        Client(
            id=client_id,
            tenant_id=tenant_id,
            name="Phase A Client",
            code="PAC",
            contact_email="client@example.com",
            settings={
                "billing_profile": {"legal_name": "Phase A Client LLC"},
                "shopify": {"webhook_secret": "client-secret"},
            },
        )
    )
    db.add(
        User(
            id="phase-a-user",
            tenant_id=tenant_id,
            email="phase-user@example.com",
            hashed_password="hash",
            full_name="Phase User",
            role=UserRole.OPERATOR.value,
            permissions=["receiving.execute"],
        )
    )
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Phase Warehouse", code="PHW"))
    db.add(
        Zone(
            id="phase-a-zone",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Ambient",
            code="A",
            sequence=1,
        )
    )
    db.add(
        Location(
            id="phase-a-location",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="phase-a-zone",
            barcode="A-01-01-01-01",
            aisle="01",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        RateCard(
            id="phase-a-rate-card",
            tenant_id=tenant_id,
            client_id=client_id,
            name="Standard",
            effective_from=datetime.now(UTC).date(),
            rules={"storage_per_pallet_day": 1.25},
        )
    )
    db.add(
        SKU(
            id="phase-a-sku",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="PHASE-A-SKU",
            barcode="123456789012",
            name="Phase A SKU",
            weight_kg=1.5,
            attributes={"shopify_api_key": "sku-secret", "color": "blue"},
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["users.manage", "master_data.manage", "billing.manage"],
        exp=datetime.now(UTC),
    )

    receiving_codes = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.receiving_codes.get", args={}),
        current_user=current_user,
        db=db,
    )
    assert receiving_codes.result["sample_code"] == "BOX-0001"

    receiving_labels = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.receiving_labels.get", args={}),
        current_user=current_user,
        db=db,
    )
    assert receiving_labels.result["fields"] == ["order_number", "sku_code", "customer_barcode"]

    users = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.users.list", args={}),
        current_user=current_user,
        db=db,
    )
    assert users.result["items"][0]["email"] == "phase-user@example.com"

    user_detail = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.users.get", args={"user_id": "phase-a-user"}),
        current_user=current_user,
        db=db,
    )
    assert user_detail.result["email"] == "phase-user@example.com"
    assert "hashed_password" not in user_detail.result
    assert "password_reset" not in str(user_detail.result)

    permissions = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.permissions.explain", args={}),
        current_user=current_user,
        db=db,
    )
    assert "billing.manage" in permissions.result["available_permissions"]

    client_profile = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.client_profile.get", args={}),
        current_user=current_user,
        db=db,
    )
    assert client_profile.result["items"][0]["settings"]["shopify"]["webhook_secret"] == "[redacted]"
    assert "client-secret" not in str(client_profile.result)

    billing = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.billing.explain", args={}),
        current_user=current_user,
        db=db,
    )
    assert billing.result["tenant_billing_profile"]["api_key"] == "[redacted]"
    assert billing.result["clients"][0]["active_rate_cards"] == 1
    assert "tenant-secret" not in str(billing.result)

    locations = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.warehouse_locations.list", args={}),
        current_user=current_user,
        db=db,
    )
    assert locations.result["items"][0]["barcode"] == "A-01-01-01-01"


    warehouse_detail = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.warehouse.get", args={"warehouse_id": warehouse_id}
        ),
        current_user=current_user,
        db=db,
    )
    assert warehouse_detail.result["zones"][0]["code"] == "A"
    assert warehouse_detail.result["locations"][0]["barcode"] == "A-01-01-01-01"

    rate_card_detail = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.rate_card.get", args={"rate_card_id": "phase-a-rate-card"}
        ),
        current_user=current_user,
        db=db,
    )
    assert rate_card_detail.result["rules"]["storage_per_pallet_day"] == 1.25

    receiving_code_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.receiving_codes.preview",
            args={"settings": {"prefix": "PKG", "sequence_padding": 2}},
        ),
        current_user=current_user,
        db=db,
    )
    assert receiving_code_preview.result["writes"] is False
    assert receiving_code_preview.result["changed_count"] >= 1
    assert receiving_code_preview.result["proposed"]["sample_code"] == "PKG-01"
    assert receiving_code_preview.result["confirmation_required_for_write"] is True
    assert receiving_code_preview.result["planned_request"]["endpoint"] == (
        "POST /api/v1/agent/settings/receiving-codes/preview"
    )
    receiving_code_token = receiving_code_preview.result["confirmation_payload"][
        "confirmation_token"
    ]

    with pytest.raises(HTTPException) as missing_idempotency:
        await confirm_settings_change_for_agent(
            "receiving-codes",
            SettingsAgentRequest(
                settings={"prefix": "PKG", "sequence_padding": 2},
                confirmation_token=receiving_code_token,
            ),
            x_idempotency_key=None,
            current_user=current_user,
            db=db,
        )
    assert missing_idempotency.value.status_code == 400
    assert missing_idempotency.value.detail["code"] == "idempotency_key_required"

    with pytest.raises(HTTPException) as wrong_token:
        await confirm_settings_change_for_agent(
            "receiving-codes",
            SettingsAgentRequest(
                settings={"prefix": "PKG", "sequence_padding": 2},
                confirmation_token="set-rcv-code:not-the-preview-token",
            ),
            x_idempotency_key="phase-b-codes-wrong-token",
            current_user=current_user,
            db=db,
        )
    assert wrong_token.value.status_code == 409
    assert wrong_token.value.detail["code"] == "confirmation_mismatch"

    with pytest.raises(HTTPException) as changed_body:
        await confirm_settings_change_for_agent(
            "receiving-codes",
            SettingsAgentRequest(
                settings={"prefix": "PKX", "sequence_padding": 2},
                confirmation_token=receiving_code_token,
            ),
            x_idempotency_key="phase-b-codes-changed-body",
            current_user=current_user,
            db=db,
        )
    assert changed_body.value.status_code == 409
    assert changed_body.value.detail["code"] == "confirmation_mismatch"

    confirmed_codes = await confirm_settings_change_for_agent(
        "receiving-codes",
        SettingsAgentRequest(
            settings={"prefix": "PKG", "sequence_padding": 2},
            confirmation_token=receiving_code_token,
        ),
        x_idempotency_key="phase-b-codes",
        current_user=current_user,
        db=db,
    )
    replayed_codes = await confirm_settings_change_for_agent(
        "receiving-codes",
        SettingsAgentRequest(
            settings={"prefix": "PKG", "sequence_padding": 2},
            confirmation_token=receiving_code_token,
        ),
        x_idempotency_key="phase-b-codes",
        current_user=current_user,
        db=db,
    )
    assert replayed_codes == confirmed_codes
    assert confirmed_codes["state_after"]["prefix"] == "PKG"
    assert confirmed_codes["state_after"]["sample_code"] == "PKG-01"
    tenant_after_codes = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant_after_codes.settings["receiving_code_rules"]["prefix"] == "PKG"

    receiving_label_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.receiving_labels.preview",
            args={"settings": {"fields": ["order_number", "tracking_number", "bad_field"]}},
        ),
        current_user=current_user,
        db=db,
    )
    assert receiving_label_preview.result["proposed"]["fields"] == [
        "order_number",
        "tracking_number",
    ]
    assert receiving_label_preview.result["confirmation_required_for_write"] is True

    confirmed_labels = await confirm_settings_change_for_agent(
        "receiving-labels",
        SettingsAgentRequest(
            settings={"fields": ["order_number", "tracking_number", "bad_field"]},
            confirmation_token=receiving_label_preview.result["confirmation_payload"][
                "confirmation_token"
            ],
        ),
        x_idempotency_key="phase-b-labels",
        current_user=current_user,
        db=db,
    )
    assert confirmed_labels["state_after"]["fields"] == ["order_number", "tracking_number"]
    tenant_after_labels = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    assert tenant_after_labels.settings["receiving_label_template"]["fields"] == [
        "order_number",
        "tracking_number",
    ]

    client_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.client_profile.preview",
            args={"client_id": client_id, "changes": {"contact_email": "new@example.com"}},
        ),
        current_user=current_user,
        db=db,
    )
    assert client_preview.result["changes"][0]["field"] == "contact_email"
    assert client_preview.result["confirmation_required_for_write"] is True

    confirmed_client = await confirm_settings_change_for_agent(
        "client-profile",
        SettingsAgentRequest(
            client_id=client_id,
            changes={"contact_email": "new@example.com"},
            confirmation_token=client_preview.result["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="phase-c-client-profile",
        current_user=current_user,
        db=db,
    )
    assert confirmed_client["changed_fields"] == ["contact_email"]
    client_after = await db.scalar(select(Client).where(Client.id == client_id))
    assert client_after.contact_email == "new@example.com"
    assert client_after.settings["shopify"]["webhook_secret"] == "client-secret"

    sku_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.sku.preview",
            args={
                "sku_id": "phase-a-sku",
                "changes": {"name": "Updated SKU", "attributes": {"api_key": "nope"}},
            },
        ),
        current_user=current_user,
        db=db,
    )
    assert sku_preview.result["changes"][0]["field"] == "name"
    assert [change["field"] for change in sku_preview.result["changes"]] == ["name"]
    assert sku_preview.result["confirmation_required_for_write"] is True
    assert "sku-secret" not in str(sku_preview.result)

    confirmed_sku = await confirm_settings_change_for_agent(
        "sku",
        SettingsAgentRequest(
            sku_id="phase-a-sku",
            changes={"name": "Updated SKU", "attributes": {"api_key": "nope"}},
            confirmation_token=sku_preview.result["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="phase-c-sku",
        current_user=current_user,
        db=db,
    )
    assert confirmed_sku["changed_fields"] == ["name"]
    sku_after = await db.scalar(select(SKU).where(SKU.id == "phase-a-sku"))
    assert sku_after.name == "Updated SKU"
    assert sku_after.attributes["shopify_api_key"] == "sku-secret"

    location_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.warehouse_location.preview",
            args={"location_id": "phase-a-location", "changes": {"current_status": "blocked"}},
        ),
        current_user=current_user,
        db=db,
    )
    assert location_preview.result["changes"][0]["field"] == "current_status"
    assert location_preview.result["confirmation_required_for_write"] is True

    confirmed_location = await confirm_settings_change_for_agent(
        "warehouse-location",
        SettingsAgentRequest(
            location_id="phase-a-location",
            changes={"current_status": "blocked"},
            confirmation_token=location_preview.result["confirmation_payload"][
                "confirmation_token"
            ],
        ),
        x_idempotency_key="phase-c-location",
        current_user=current_user,
        db=db,
    )
    assert confirmed_location["changed_fields"] == ["current_status"]
    location_after = await db.scalar(select(Location).where(Location.id == "phase-a-location"))
    assert location_after.current_status == LocationStatus.BLOCKED.value

    with pytest.raises(HTTPException) as invalid_location:
        await run_agent_tool(
            AgentToolRunRequest(
                tool_name="settings.warehouse_location.preview",
                args={
                    "location_id": "phase-a-location",
                    "changes": {"current_status": "lost"},
                },
            ),
            current_user=current_user,
            db=db,
        )
    assert invalid_location.value.status_code == 400

    rate_card_preview = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.billing_rate_card.preview",
            args={
                "rate_card_id": "phase-a-rate-card",
                "changes": {"rules": {"storage_per_pallet_day": 1.5}},
            },
        ),
        current_user=current_user,
        db=db,
    )
    assert rate_card_preview.result["changes"][0]["field"] == "rules"


@pytest.mark.asyncio
async def test_platform_admin_agent_user_list_is_cross_tenant(
    db: AsyncSession,
    tenant_id: str,
):
    db.add_all(
        [
            Tenant(
                id=tenant_id,
                name="Platform Console Tenant",
                code="PCT",
                contact_email="platform-console@example.com",
                settings={
                    "agent_console": {
                        "enabled": True,
                        "allowed_tools": ["settings.users.list"],
                    }
                },
            ),
            Tenant(
                id="cross-tenant-user-list",
                name="Cross Tenant",
                code="CTL",
                contact_email="cross-tenant@example.com",
            ),
            User(
                id="platform-console-user",
                tenant_id=tenant_id,
                email="platform-console-user@example.com",
                hashed_password="hash",
                full_name="Platform Console User",
                role=UserRole.TENANT_ADMIN.value,
                permissions=["users.manage"],
            ),
            User(
                id="cross-tenant-user",
                tenant_id="cross-tenant-user-list",
                email="cross-tenant-user@example.com",
                hashed_password="hash",
                full_name="Cross Tenant User",
                role=UserRole.OPERATOR.value,
                permissions=["receiving.execute"],
            ),
        ]
    )
    await db.flush()

    response = await run_agent_tool(
        AgentToolRunRequest(tool_name="settings.users.list", args={"limit": 20}),
        current_user=TokenPayload(
            sub="platform-console-user",
            tenant_id=tenant_id,
            client_id=None,
            role=UserRole.PLATFORM_ADMIN,
            permissions=[],
            exp=datetime.now(UTC),
        ),
        db=db,
    )

    assert response.result["count"] == 2
    assert {item["tenant_id"] for item in response.result["items"]} == {
        tenant_id,
        "cross-tenant-user-list",
    }


@pytest.mark.asyncio
async def test_agent_warehouse_blueprint_preview_and_confirm_create_dallas_layout(
    db: AsyncSession,
    tenant_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Dallas Blueprint Tenant",
            code="DBT",
            contact_email="ops@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": [
                        "warehouse.blueprint.preview",
                        "settings.warehouse.get",
                        "settings.warehouse_locations.list",
                    ],
                }
            },
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["master_data.manage"],
        exp=datetime.now(UTC),
    )
    blueprint_args = {
        "warehouse": {"name": "Dallas Warehouse", "code": "DAL", "timezone": "America/Chicago"},
        "source_image_name": "WAREHOUSE L-SHAPE v3",
        "notes": "ABC are floor storage. Only the top row near the office is 4-level rack storage.",
        "layout": {"shape": "L", "drive_aisle_ft": {"width": 40, "length": 165}},
        "planning_standard": {"document": "docs/36-agv-planning-standard.md"},
        "route_policy": {
            "traffic_pattern": "controlled_one_way_loop",
            "main_aisle_width_ft": 40,
            "branch_aisle_width_ft": 12,
            "abc_lower_lane_width_ft": 12,
            "minimum_turning_radius_mm": 800,
            "fork_to_pallet_clearance_mm": 500,
            "storage_handoff_strategy": "edge_handoff_with_a_area_connector",
            "agv_enters_floor_storage": False,
            "dock_doors_are_storage_locations": False,
            "left_side_enclosed": True,
            "a_area_connector_width_ft": 12,
        },
        "route_nodes": [
            {"id": "N-DOCK-27", "x": 86, "y": 60, "label": "Dock 27 approach"},
            {"id": "N-DOCK-NORTH", "x": 86, "y": 26.25, "label": "Dock corridor north"},
            {"id": "N-TOP-C", "x": 67.33, "y": 26.25, "label": "Top aisle C edge"},
            {"id": "N-TOP-B", "x": 42, "y": 26.25, "label": "Top aisle B edge"},
            {"id": "N-TOP-A", "x": 29.33, "y": 26.25, "label": "Top aisle A east edge"},
            {"id": "N-A-CONN-TOP", "x": 7.8, "y": 26.25, "label": "A connector top"},
            {"id": "N-A-FACE", "x": 20.47, "y": 26.25, "label": "A north edge handoff"},
            {"id": "N-B-FACE", "x": 42, "y": 26.25, "label": "B north edge handoff"},
            {"id": "N-C-FACE", "x": 67.33, "y": 26.25, "label": "C north edge handoff"},
            {"id": "N-A-CONN-LOWER", "x": 7.8, "y": 50.26, "label": "A connector lower"},
            {"id": "N-A-EXIT", "x": 20.47, "y": 50.26, "label": "A return lane"},
            {"id": "N-B-EXIT", "x": 42, "y": 50.26, "label": "B return lane"},
            {"id": "N-C-EXIT", "x": 67.33, "y": 50.26, "label": "C return lane"},
            {"id": "N-ABC-LOWER-LANE", "x": 42, "y": 50.26, "label": "ABC lower AGV lane"},
            {"id": "N-RETURN-CORRIDOR", "x": 86, "y": 50.26, "label": "Return corridor entry"},
        ],
        "agv_paths": [
            {
                "id": "PATH-DOCK-CORRIDOR-UP",
                "role": "main_aisle",
                "direction": "northbound",
                "lane_policy": "one_way",
                "width_ft": 40,
                "points": ["N-DOCK-27", "N-DOCK-NORTH"],
            },
            {
                "id": "PATH-TOP-AISLE-WEST",
                "role": "main_aisle",
                "direction": "westbound",
                "lane_policy": "one_way",
                "width_ft": 12,
                "points": [
                    "N-DOCK-NORTH",
                    "N-TOP-C",
                    "N-C-FACE",
                    "N-TOP-B",
                    "N-B-FACE",
                    "N-TOP-A",
                    "N-A-FACE",
                    "N-A-CONN-TOP",
                ],
            },
            {
                "id": "PATH-A-CONNECTOR-DOWN",
                "role": "connector_aisle",
                "direction": "southbound",
                "lane_policy": "one_way",
                "width_ft": 12,
                "points": ["N-A-CONN-TOP", "N-A-CONN-LOWER"],
            },
            {
                "id": "PATH-ABC-LOWER-LANE",
                "role": "return_lane",
                "direction": "eastbound_to_dock",
                "lane_policy": "controlled_one_way",
                "width_ft": 12,
                "points": [
                    "N-A-CONN-LOWER",
                    "N-A-EXIT",
                    "N-B-EXIT",
                    "N-ABC-LOWER-LANE",
                    "N-C-EXIT",
                    "N-RETURN-CORRIDOR",
                ],
            },
        ],
        "stations": [
            {
                "code": "WAIT-DOCK",
                "name": "Dock wait point",
                "station_role": "wait",
                "x": 86,
                "y": 33,
                "route_anchor_id": "N-DOCK-27",
                "docking_direction": "north",
            },
            {
                "code": "CHG-01",
                "name": "Charging station 01",
                "station_role": "charging",
                "x": 83,
                "y": 94,
                "route_anchor_id": "N-DOCK-27",
                "docking_direction": "south",
            },
        ],
        "safety_zones": [
            {
                "code": "SLOW-DOCK-CORRIDOR",
                "zone_type": "slow_zone",
                "x": 82,
                "y": 33,
                "width": 8,
                "height": 60,
            }
        ],
        "zones": [
            {
                "name": "Dallas A",
                "code": "DAL-A",
                "type": "floor_storage",
                "x": 11.6,
                "y": 30.5,
                "w": 17.73,
                "h": 15.53,
                "rows": 4,
                "columns": 4,
                "levels": 1,
                "positions": 1,
                "storage_profile": "oversize_floor_load",
                "width_ft": 6,
                "depth_ft": 5,
                "height_ft": 9,
                "dimensions": {
                    "zone_width_ft": 28,
                    "zone_depth_ft": 22,
                    "area_sqft": 616,
                    "storage_unit": "oversize_floor_load",
                    "width_ft": 6,
                    "depth_ft": 5,
                    "height_ft": 9,
                    "cargo_size_in": {"length": 68, "width": 58, "height": 100},
                    "planned_orientation": "68in side runs across zone width, 58in side runs depth",
                    "slot_count": 16,
                    "slot_area_sqft": 30,
                    "slot_layout": {
                        "rows": 4,
                        "columns": 4,
                        "slot_width_ft": 6,
                        "slot_depth_ft": 5,
                        "offset_x_ft": 0,
                        "offset_y_ft": 0,
                        "occupied_width_ft": 24,
                        "occupied_depth_ft": 20,
                        "residual_width_ft": 4,
                        "residual_depth_ft": 2,
                        "total_slot_footprint_sqft": 480,
                    },
                    "capacity_adjustment": {
                        "original_width_ft": 40,
                        "original_storage_depth_ft": 22,
                        "original_area_sqft": 880,
                        "original_slot_count": 24,
                        "lost_to_agv_connector_width_ft": 12,
                        "lost_to_agv_connector_area_sqft": 264,
                        "lost_storage_area_sqft": 264,
                        "slot_delta": -8,
                        "reason": "A cargo footprint is 68x58x100 in and cannot fit in GMA 48x40 in slots.",
                    },
                },
                "layout_metadata": {
                    "route_role": "floor_storage_lane",
                    "lane_policy": "one_agv_one_way",
                    "agv_internal_travel": False,
                    "handoff_strategy": "edge_handoff_with_a_area_connector",
                    "docking_direction": "north",
                    "connector_zone_code": "A-CONN",
                    "route_anchor_id": "N-A-FACE",
                    "route_exit_id": "N-A-EXIT",
                },
                "expected_pcs": 16,
            },
            {
                "name": "Dallas B",
                "code": "DAL-B",
                "type": "floor_storage",
                "x": 29.33,
                "y": 30.5,
                "w": 25.33,
                "h": 15.53,
                "rows": 4,
                "columns": 4,
                "levels": 1,
                "positions": 1,
                "metadata": {
                    "storage_profile": "oversize_floor_load",
                    "rows": 4,
                    "columns": 4,
                    "expected_pcs": 16,
                    "route_role": "floor_storage_lane",
                    "lane_policy": "one_agv_one_way",
                    "agv_internal_travel": False,
                    "handoff_strategy": "external_edge_handoff",
                    "docking_direction": "north",
                    "route_anchor_id": "N-B-FACE",
                    "route_exit_id": "N-B-EXIT",
                },
                "dimensions": {
                    "width_ft": 9,
                    "depth_ft": 5,
                    "height_ft": 9,
                    "zone_width_ft": 40,
                    "zone_depth_ft": 22,
                    "area_sqft": 880,
                    "storage_unit": "oversize_floor_load",
                    "cargo_size_in": {"length": 104, "width": 55, "height": 98},
                    "planned_orientation": "104in side runs across zone width, 55in side runs depth",
                    "slot_count": 16,
                    "slot_area_sqft": 45,
                    "slot_layout": {
                        "rows": 4,
                        "columns": 4,
                        "slot_width_ft": 9,
                        "slot_depth_ft": 5,
                        "offset_x_ft": 0,
                        "offset_y_ft": 0,
                        "occupied_width_ft": 36,
                        "occupied_depth_ft": 20,
                        "residual_width_ft": 4,
                        "residual_depth_ft": 2,
                        "total_slot_footprint_sqft": 720,
                    },
                },
            },
            {
                "name": "Dallas C",
                "code": "DAL-C",
                "type": "floor_storage",
                "x": 54.67,
                "y": 30.5,
                "w": 25.33,
                "h": 15.53,
                "rows": 4,
                "columns": 4,
                "levels": 1,
                "positions": 1,
                "storage_profile": "oversize_floor_load",
                "width_ft": 9,
                "depth_ft": 5,
                "height_ft": 9,
                "dimensions": {
                    "zone_width_ft": 40,
                    "zone_depth_ft": 22,
                    "area_sqft": 880,
                    "storage_unit": "oversize_floor_load",
                    "width_ft": 9,
                    "depth_ft": 5,
                    "height_ft": 9,
                    "cargo_size_in": {"length": 104, "width": 55, "height": 98},
                    "planned_orientation": "104in side runs across zone width, 55in side runs depth",
                    "slot_count": 16,
                    "slot_area_sqft": 45,
                    "slot_layout": {
                        "rows": 4,
                        "columns": 4,
                        "slot_width_ft": 9,
                        "slot_depth_ft": 5,
                        "offset_x_ft": 0,
                        "offset_y_ft": 0,
                        "occupied_width_ft": 36,
                        "occupied_depth_ft": 20,
                        "residual_width_ft": 4,
                        "residual_depth_ft": 2,
                        "total_slot_footprint_sqft": 720,
                    },
                },
                "layout_metadata": {
                    "route_role": "floor_storage_lane",
                    "lane_policy": "one_agv_one_way",
                    "agv_internal_travel": False,
                    "handoff_strategy": "external_edge_handoff",
                    "docking_direction": "north",
                    "route_anchor_id": "N-C-FACE",
                    "route_exit_id": "N-C-EXIT",
                },
                "expected_pcs": 16,
            },
            {
                "name": "Top Rack Row",
                "code": "DAL-RACK",
                "type": "rack_storage",
                "x": 4,
                "y": 15,
                "w": 76,
                "h": 7,
                "rows": 4,
                "aisles": 1,
                "columns": 15,
                "positions": 1,
                "layout_metadata": {
                    "route_role": "top_rack_face",
                    "docking_direction": "south",
                    "route_anchor_id": "N-RACK-FACE",
                    "route_exit_id": "N-RACK-FACE",
                },
                "pallet": "GMA",
                "pallet_width_in": 48,
                "pallet_depth_in": 40,
                "pallet_depth_ft": 3.33,
                "level_clear_height_in": 65,
                "level_clear_height_ft": 5.42,
                "bay_count": 15,
                "bay_width_ft": 8,
                "expected_pcs": 60,
            },
            {
                "name": "Drive Aisle",
                "code": "DRV",
                "type": "drive_aisle",
                "x": 82,
                "y": 22,
                "w": 6,
                "h": 70,
                "width_ft": 40,
                "length_ft": 165,
                "layout_metadata": {
                    "route_role": "main_aisle",
                    "lane_policy": "controlled_one_way",
                    "direction": "northbound_to_top_aisle",
                },
            },
            {
                "name": "ABC Lower AGV Lane",
                "code": "ABC-LOWER",
                "type": "drive_aisle",
                "x": 4,
                "y": 46.03,
                "w": 84,
                "h": 8.47,
                "width_ft": 12,
                "layout_metadata": {
                    "route_role": "lower_return_lane",
                    "lane_policy": "controlled_one_way",
                    "direction": "eastbound_to_dock",
                    "route_anchor_id": "N-ABC-LOWER-LANE",
                },
            },
            {
                "name": "A Area AGV Connector",
                "code": "A-CONN",
                "type": "drive_aisle",
                "x": 4,
                "y": 22,
                "w": 7.6,
                "h": 32.5,
                "width_ft": 12,
                "length_ft": 46,
                "layout_metadata": {
                    "route_role": "internal_agv_connector",
                    "lane_policy": "controlled_one_way",
                    "direction": "southbound_to_lower_lane",
                    "left_side_enclosed": True,
                    "replaces_original_a_storage_width_ft": 12,
                    "route_anchor_id": "N-A-CONN-TOP",
                    "route_exit_id": "N-A-CONN-LOWER",
                },
            },
            {
                "name": "Dock Doors",
                "code": "DOCK",
                "type": "dock",
                "x": 90,
                "y": 35,
                "w": 6,
                "h": 55,
                "racks": 8,
                "doors": "23-30",
                "exit": "27",
                "layout_metadata": {
                    "route_role": "external_transport_interface",
                    "station_role": "inbound_outbound",
                    "docking_direction": "west",
                    "dock_doors_are_storage_locations": False,
                },
            },
        ],
    }

    preview = await run_agent_tool(
        AgentToolRunRequest(tool_name="warehouse.blueprint.preview", args=blueprint_args),
        current_user=current_user,
        db=db,
    )
    assert preview.result["ok"] is True
    assert preview.result["summary"]["location_count"] == 108
    assert preview.result["summary"]["will_create_zones"] == 4
    assert preview.result["summary"]["will_create_warehouse"] is True
    assert preview.result["summary"]["dock_door_count"] == 8
    assert preview.result["summary"]["wcs_point_mapping_draft_count"] == 118
    assert len(preview.result["abc_floor_areas"]) == 3
    assert preview.result["abc_floor_areas"][0]["dimensions"]["width_ft"] == 6.0
    assert preview.result["abc_floor_areas"][0]["dimensions"]["depth_ft"] == 5.0
    assert preview.result["abc_floor_areas"][0]["dimensions"]["zone_depth_ft"] == 22
    assert preview.result["abc_floor_areas"][0]["dimensions"]["slot_count"] == 16
    assert (
        preview.result["abc_floor_areas"][0]["dimensions"]["capacity_adjustment"][
            "lost_to_agv_connector_width_ft"
        ]
        == 12
    )
    assert preview.result["rack_areas"][0]["code"] == "DAL-RACK"
    assert preview.result["rack_areas"][0]["dimensions"]["pallet_width_in"] == 48.0
    assert preview.result["rack_areas"][0]["dimensions"]["pallet_width_ft"] == 4.0
    assert preview.result["rack_areas"][0]["dimensions"]["pallet_depth_in"] == 40.0
    assert preview.result["rack_areas"][0]["dimensions"]["pallet_depth_ft"] == 3.33
    assert preview.result["rack_areas"][0]["dimensions"]["level_clear_height_in"] == 65.0
    assert preview.result["rack_areas"][0]["dimensions"]["bay_count"] == 15
    assert preview.result["dock_doors"][0]["code"] == "DOCK-23"
    assert preview.result["dock_doors"][-1]["code"] == "DOCK-30"
    assert preview.result["wcs_point_mapping_draft"][0]["point_code"].startswith("DAL-STO-")
    assert preview.result["wcs_point_mapping_draft"][-1]["point_type"] == "agv_station"
    assert preview.result["wcs_point_mapping_draft"][-1]["virtual"] is True
    assert preview.result["route_policy"]["dock_doors_are_storage_locations"] is False
    assert preview.result["route_policy"]["abc_lower_lane_width_ft"] == 12
    assert preview.result["route_policy"]["agv_enters_floor_storage"] is False
    assert preview.result["agv_planning"]["planning_standard"]["document"] == "docs/36-agv-planning-standard.md"
    assert len(preview.result["agv_paths"]) == 4
    assert len(preview.result["stations"]) == 2
    assert preview.result["confirmation_required_for_write"] is True
    assert all(check["ok"] for check in preview.result["validation"])

    confirmed = await confirm_warehouse_blueprint_for_agent(
        WarehouseBlueprintAgentRequest(
            **blueprint_args,
            confirmation_token=preview.result["confirmation_payload"]["confirmation_token"],
        ),
        x_idempotency_key="dallas-blueprint-confirm",
        current_user=current_user,
        db=db,
    )
    assert confirmed["created_location_count"] == 108
    warehouse = await db.scalar(
        select(Warehouse).where(Warehouse.tenant_id == tenant_id, Warehouse.code == "DAL")
    )
    assert warehouse is not None
    assert warehouse.address["_blueprint_layout"]["zones"][0]["metadata"]["storage_profile"] == "oversize_floor_load"
    assert warehouse.address["_blueprint_layout"]["zones"][0]["metadata"]["rows"] == 4
    assert warehouse.address["_blueprint_layout"]["zones"][0]["metadata"]["columns"] == 4
    assert warehouse.address["_blueprint_layout"]["zones"][0]["dimensions"]["height_ft"] == 9
    first_location_metadata = warehouse.address["_blueprint_location_metadata"][
        "DAL-A-01-01-01-01"
    ]
    assert first_location_metadata["zone_layout_percent"] == {
        "x": 11.6,
        "y": 30.5,
        "width": 17.73,
        "height": 15.53,
    }
    assert first_location_metadata["layout_percent"]["x"] == pytest.approx(11.6)
    assert first_location_metadata["layout_percent"]["y"] == pytest.approx(30.5)
    assert first_location_metadata["layout_percent"]["width"] == pytest.approx(3.799, abs=0.002)
    assert first_location_metadata["layout_percent"]["height"] == pytest.approx(3.53, abs=0.002)
    assert first_location_metadata["slot_layout_percent"]["x"] == pytest.approx(0.0)
    assert first_location_metadata["slot_layout_percent"]["y"] == pytest.approx(0.0)
    assert first_location_metadata["slot_layout_percent"]["width"] == pytest.approx(3.799, abs=0.002)
    assert first_location_metadata["slot_layout_percent"]["height"] == pytest.approx(3.53, abs=0.002)
    assert first_location_metadata["route_anchor_id"] == "N-A-FACE"
    assert first_location_metadata["docking_direction"] == "north"
    assert first_location_metadata["handoff_strategy"] == "edge_handoff_with_a_area_connector"
    assert warehouse.address["_blueprint_layout"]["route_policy"]["traffic_pattern"] == "controlled_one_way_loop"
    assert len(warehouse.address["_blueprint_layout"]["agv_paths"]) == 4
    assert len(warehouse.address["_blueprint_layout"]["safety_zones"]) == 1
    assert warehouse.address["_blueprint_layout"]["access_points"][0]["code"] == "DRV"
    assert warehouse.address["_blueprint_layout"]["access_points"][1]["code"] == "ABC-LOWER"
    assert warehouse.address["_blueprint_layout"]["access_points"][1]["metadata"]["route_role"] == "lower_return_lane"
    assert warehouse.address["_blueprint_layout"]["access_points"][2]["code"] == "A-CONN"
    assert warehouse.address["_blueprint_layout"]["access_points"][2]["metadata"]["route_role"] == "internal_agv_connector"
    assert warehouse.address["_blueprint_layout"]["access_points"][3]["code"] == "DOCK"
    assert warehouse.address["_blueprint_layout"]["access_points"][3]["agv_usage"] == (
        "unload_and_ship"
    )
    assert len(warehouse.address["_blueprint_layout"]["dock_doors"]) == 8
    assert len(warehouse.address["_blueprint_layout"]["wcs_point_mapping_draft"]) == 118
    assert len(
        (
            await db.execute(
                select(Location).where(
                    Location.tenant_id == tenant_id,
                    Location.warehouse_id == warehouse.id,
                )
            )
        ).scalars().all()
    ) == 108
    created_zones = (
        await db.execute(
            select(Zone).where(Zone.tenant_id == tenant_id, Zone.warehouse_id == warehouse.id)
        )
    ).scalars().all()
    assert len(created_zones) == 4
    first_zone = next(zone for zone in created_zones if zone.code == "DAL-A")
    assert first_zone.zone_type == "floor_storage"
    assert first_zone.dimensions["height_ft"] == 9
    assert first_zone.dimensions["slot_count"] == 16
    assert first_zone.dimensions["capacity_adjustment"]["slot_delta"] == -8
    assert first_zone.layout_metadata["coordinate_system"] == "drawing_percent"
    assert first_zone.layout_metadata["route_anchor_id"] == "N-A-FACE"
    assert first_zone.layout_metadata["agv_internal_travel"] is False
    assert first_zone.drawing_source["source_name"] == "WAREHOUSE L-SHAPE v3"
    first_location = await db.scalar(
        select(Location).where(
            Location.tenant_id == tenant_id,
            Location.warehouse_id == warehouse.id,
            Location.barcode == "DAL-A-01-01-01-01",
        )
    )
    assert first_location is not None
    assert first_location.is_agv_accessible is True
    assert first_location.dimensions["width_ft"] == 6.0
    assert first_location.dimensions["depth_ft"] == 5.0
    assert first_location.dimensions["height_ft"] == 9.0
    assert first_location.layout_metadata["coordinate_system"] == "drawing_percent"
    assert first_location.drawing_source["zone_code"] == "DAL-A"
    assert first_location.wcs_point_metadata["draft_point_code"].startswith("DAL-STO-")
    assert first_location.wcs_point_metadata["route_anchor_id"] == "N-A-FACE"
    assert first_location.wcs_point_metadata["handoff_strategy"] == "edge_handoff_with_a_area_connector"
    assert first_location.wcs_point_metadata["point_code"] is None
    rack_zone = next(zone for zone in created_zones if zone.code == "DAL-RACK")
    assert rack_zone.dimensions["pallet_width_in"] == 48.0
    assert rack_zone.dimensions["pallet_depth_in"] == 40.0
    assert rack_zone.dimensions["level_clear_height_in"] == 65.0
    wcs_draft_validation = await validate_wcs_point_mappings(
        body=WcsPointMappingRequest(
            warehouse_id=warehouse.id,
            mappings=[
                WcsPointMapping(**row)
                for row in preview.result["wcs_point_mapping_draft"]
            ],
        ),
        current_user=current_user,
        db=db,
    )
    assert wcs_draft_validation["ok"] is True
    assert wcs_draft_validation["summary"]["mapped_locations"] == 108
    assert wcs_draft_validation["summary"]["external_points"] == 10
    assert len(
        (
            await db.execute(
                select(Zone).where(Zone.tenant_id == tenant_id, Zone.warehouse_id == warehouse.id)
            )
        ).scalars().all()
    ) == 4
    warehouse_detail = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.warehouse.get", args={"warehouse_id": warehouse.id}
        ),
        current_user=current_user,
        db=db,
    )
    assert warehouse_detail.result["zones"][0]["blueprint_metadata"]["dimensions"][
        "height_ft"
    ] == 9
    locations = await run_agent_tool(
        AgentToolRunRequest(
            tool_name="settings.warehouse_locations.list", args={"warehouse_id": warehouse.id}
        ),
        current_user=current_user,
        db=db,
    )
    assert locations.result["items"][0]["blueprint_metadata"]["dimensions"]["width_ft"] == 6.0
    assert locations.result["items"][0]["blueprint_metadata"]["layout_percent"]["x"] == 11.6
    assert locations.result["items"][0]["coordinate_x"] is not None
    assert not [
        item
        for item in locations.result["items"]
        if item["zone_code"] == "DOCK" or item["location_type"] == LocationType.DOCK.value
    ]


@pytest.mark.asyncio
async def test_agent_import_writes_are_not_direct_agent_tools(
    db: AsyncSession,
    tenant_id: str,
):
    assert not (DIRECT_IMPORT_WRITE_TOOLS & set(DEFAULT_ALLOWED_TOOLS))
    db.add(
        Tenant(
            id=tenant_id,
            name="Agent Tenant",
            code="AGT",
            contact_email="ops@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "allowed_tools": sorted(DIRECT_IMPORT_WRITE_TOOLS),
                }
            },
        )
    )
    await db.flush()
    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=[
            "inbound_orders.import",
            "outbound_orders.manage",
            "master_data.manage",
        ],
        exp=datetime.now(UTC),
    )

    for tool_name in sorted(DIRECT_IMPORT_WRITE_TOOLS):
        with pytest.raises(HTTPException) as exc:
            await run_agent_tool(
                AgentToolRunRequest(
                    tool_name=tool_name,
                    args={"confirmed": True, "csv_text": "header\nvalue\n"},
                ),
                current_user=current_user,
                db=db,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "agent_write_gate_required"


@pytest.mark.asyncio
async def test_agent_inventory_explain_requires_provider_configuration(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Agent Tenant",
            code="AGT",
            contact_email="ops@example.com",
            settings={"agent_console": {"enabled": True, "allowed_tools": ["inventory.explain"]}},
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Acme", code="ACME"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Main", code="MAIN"))
    db.add(
        SKU(
            id="sku-agent-1",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-AGENT",
            name="Agent SKU",
        )
    )
    await db.flush()

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["master_data.manage"],
        exp=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc:
        await run_agent_tool(
            AgentToolRunRequest(tool_name="inventory.explain", args={"query": "SKU-AGENT"}),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 400
    assert "provider" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_agent_inventory_explain_uses_configured_model_service(
    db: AsyncSession,
    tenant_id: str,
    client_id: str,
    warehouse_id: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db.add(
        Tenant(
            id=tenant_id,
            name="Agent Tenant",
            code="AGT",
            contact_email="ops@example.com",
            settings={
                "agent_console": {
                    "enabled": True,
                    "provider_type": "minimax",
                    "provider_label": "MiniMax Production",
                    "base_url": "https://api.minimaxi.com/v1",
                    "model_name": "MiniMax-M1",
                    "api_key": "secret",
                    "allowed_tools": ["inventory.explain"],
                }
            },
        )
    )
    db.add(Client(id=client_id, tenant_id=tenant_id, name="Acme", code="ACME"))
    db.add(Warehouse(id=warehouse_id, tenant_id=tenant_id, name="Main", code="MAIN"))
    db.add(
        Zone(
            id="zone-agent-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            name="Zone 1",
            code="Z1",
        )
    )
    db.add(
        Location(
            id="loc-agent-1",
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            zone_id="zone-agent-1",
            barcode="A-01-01-01-01",
            aisle="A",
            rack="01",
            level="01",
            position="01",
            location_type=LocationType.STORAGE.value,
            current_status=LocationStatus.AVAILABLE.value,
        )
    )
    db.add(
        SKU(
            id="sku-agent-2",
            tenant_id=tenant_id,
            client_id=client_id,
            sku_code="SKU-AGENT",
            name="Agent SKU",
        )
    )
    db.add(
        Inventory(
            id="inv-agent-1",
            tenant_id=tenant_id,
            client_id=client_id,
            warehouse_id=warehouse_id,
            location_id="loc-agent-1",
            sku_id="sku-agent-2",
            quantity_on_hand=12,
            quantity_allocated=2,
        )
    )
    await db.flush()

    async def fake_explain_inventory(
        self, query: str, inventory_payload: dict, language: str | None = None
    ):
        return {
            "query": query,
            "provider_type": self.provider_type,
            "provider_label": self.provider_label,
            "model_name": self.model_name,
            "items_considered": len(inventory_payload.get("items", [])),
            "source_count": inventory_payload.get("count", 0),
            "language": language,
            "answer": "Stock is healthy and there is low allocation pressure.",
        }

    monkeypatch.setattr(
        "app.services.agent_model_service.AgentModelService.explain_inventory",
        fake_explain_inventory,
    )

    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id=tenant_id,
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["master_data.manage"],
        exp=datetime.now(UTC),
    )

    response = await run_agent_tool(
        AgentToolRunRequest(tool_name="inventory.explain", args={"query": "SKU-AGENT"}),
        current_user=current_user,
        db=db,
    )

    assert response.tool_name == "inventory.explain"
    assert response.result["provider_type"] == "minimax"
    assert response.result["model_name"] == "MiniMax-M1"
    assert "healthy" in response.result["answer"]


@pytest.mark.asyncio
async def test_agent_model_service_rewrites_inventory_answer_to_requested_language(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.agent_model_service import AgentModelService

    service = AgentModelService(
        {
            "provider_type": "minimax",
            "provider_label": "MiniMax Production",
            "base_url": "https://api.minimaxi.com/v1",
            "model_name": "MiniMax-M1",
            "api_key": "secret",
        }
    )

    calls: list[tuple[str, str]] = []

    async def fake_generate_text(system_prompt: str, user_prompt: str):
        calls.append((system_prompt, user_prompt))
        if len(calls) == 1:
            return (
                "**1. What the inventory picture says**\n"
                "All inventory is available.\n\n"
                "**2. Pressure or risk worth noticing**\n"
                "No immediate pressure.\n\n"
                "**3. Suggested next step**\n"
                "Review demand."
            )
        return (
            "1. 庫存概況\n"
            "目前庫存都可用。\n\n"
            "2. 風險提醒\n"
            "目前沒有明顯壓力。\n\n"
            "3. 建議下一步\n"
            "再檢查需求。"
        )

    monkeypatch.setattr(service, "_generate_text", fake_generate_text)

    result = await service.explain_inventory(
        "DAN",
        {"count": 1, "items": [{"sku_code": "SKU-1", "quantity_on_hand": 10}]},
        "zh-Hant",
    )

    assert len(calls) == 2
    assert "Traditional Chinese" in calls[1][0]
    assert "庫存概況" in result["answer"]


@pytest.mark.asyncio
async def test_agent_model_service_routes_deepseek_through_openai_style(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.agent_model_service import AgentModelService

    service = AgentModelService(
        {
            "provider_type": "deepseek",
            "provider_label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
            "api_key": "deepseek-secret",
        }
    )
    calls: list[tuple[str, str]] = []

    async def fake_call_openai_style(system_prompt: str, user_prompt: str):
        calls.append((system_prompt, user_prompt))
        return "DeepSeek handled the inventory request."

    monkeypatch.setattr(service, "_call_openai_style", fake_call_openai_style)

    result = await service.explain_inventory(
        "overview",
        {"count": 0, "items": []},
        "en",
    )

    assert calls
    assert result["provider_type"] == "deepseek"
    assert result["model_name"] == "deepseek-v4-flash"
    assert "DeepSeek handled" in result["answer"]


@pytest.mark.asyncio
async def test_agent_model_service_calls_deepseek_chat_completions(monkeypatch: pytest.MonkeyPatch):
    from app.services.agent_model_service import AgentModelService

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "OK from DeepSeek"}}]}

    class FakeClient:
        def __init__(self, timeout: int):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.agent_model_service.httpx.AsyncClient", FakeClient)

    service = AgentModelService(
        {
            "provider_type": "deepseek",
            "provider_label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
            "api_key": "deepseek-secret",
        }
    )

    answer = await service._call_openai_style("system", "user")

    assert answer == "OK from DeepSeek"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer deepseek-secret",
    }
    assert captured["json"] == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "temperature": 0.2,
    }


@pytest.mark.asyncio
async def test_agent_model_service_deepseek_runs_web_search_tool(
    monkeypatch: pytest.MonkeyPatch,
):
    import copy

    from app.core.config import settings
    from app.services.agent_model_service import AgentModelService

    monkeypatch.setattr(settings, "DEEPSEEK_WEB_SEARCH_ENABLED", True)
    monkeypatch.setattr(settings, "WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "tvly-secret")

    captured_posts: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload: dict):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, timeout: int):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            captured_posts.append(copy.deepcopy(json))
            if len(captured_posts) == 1:
                return FakeResponse(
                    {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "web_search",
                                                "arguments": '{"query":"latest lithium battery price","max_results":2}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                )
            return FakeResponse(
                {"choices": [{"finish_reason": "stop", "message": {"content": "Search-backed answer."}}]}
            )

    async def fake_execute_web_search_tool(name, raw_arguments):
        assert name == "web_search"
        assert "latest lithium battery price" in raw_arguments
        return '{"results":[{"title":"Source","url":"https://example.com","content":"Snippet"}]}'

    monkeypatch.setattr("app.services.agent_model_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(
        "app.services.agent_model_service.execute_web_search_tool",
        fake_execute_web_search_tool,
    )

    service = AgentModelService(
        {
            "provider_type": "deepseek",
            "provider_label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
            "api_key": "deepseek-secret",
        }
    )

    answer = await service._call_openai_style("system", "user asks latest price")

    assert answer == "Search-backed answer."
    assert "tools" in captured_posts[0]
    assert captured_posts[0]["tool_choice"] == "auto"
    assert captured_posts[1]["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"results":[{"title":"Source","url":"https://example.com","content":"Snippet"}]}',
    }


@pytest.mark.asyncio
async def test_agent_model_service_rejects_null_deepseek_content(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services.agent_model_service import AgentModelService

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": None}}]}

    class FakeClient:
        def __init__(self, timeout: int):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr("app.services.agent_model_service.httpx.AsyncClient", FakeClient)

    service = AgentModelService(
        {
            "provider_type": "deepseek",
            "provider_label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash",
            "api_key": "deepseek-secret",
        }
    )

    with pytest.raises(HTTPException) as exc:
        await service._call_openai_style("system", "user")

    assert exc.value.status_code == 502
    assert "missing message content" in str(exc.value.detail)
    assert "finish_reason=stop" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_agent_team_status_returns_empty_when_no_external_agents_configured(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    monkeypatch.setattr(settings, "KIMI_API_KEY", "")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")

    current_user = TokenPayload(
        sub="platform-admin",
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    response = await agent_team_status(current_user=current_user)

    assert response == {"agents": []}


@pytest.mark.asyncio
async def test_agent_team_status_returns_deepseek_when_configured(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    monkeypatch.setattr(settings, "KIMI_API_KEY", "")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "deepseek-v4-flash")

    current_user = TokenPayload(
        sub="platform-admin",
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    response = await agent_team_status(current_user=current_user)

    assert response == {
        "agents": [
            {
                "key": "deepseek",
                "label": "DeepSeek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "configured": True,
            }
        ]
    }


@pytest.mark.asyncio
async def test_agent_team_rejects_null_deepseek_content(monkeypatch: pytest.MonkeyPatch):
    from app.services.agent_team_service import ExternalAgentConfig

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"finish_reason": "content_filter", "message": {"content": None}}]}

    class FakeClient:
        def __init__(self, timeout: int):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr("app.services.agent_team_service.httpx.AsyncClient", FakeClient)

    service = AgentTeamService()
    config = ExternalAgentConfig(
        key="deepseek",
        label="DeepSeek",
        api_key="deepseek-secret",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )

    with pytest.raises(HTTPException) as exc:
        await service._call_openai_style(config, "system", "user")

    assert exc.value.status_code == 502
    assert "DeepSeek returned no message content" in str(exc.value.detail)
    assert "finish_reason=content_filter" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_agent_team_run_returns_parallel_answers_and_synthesis(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "minimax-secret")
    monkeypatch.setattr(settings, "QWEN_API_KEY", "qwen-secret")
    monkeypatch.setattr(settings, "KIMI_API_KEY", "kimi-secret")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setattr(settings, "MINIMAX_MODEL", "MiniMax-M1")
    monkeypatch.setattr(settings, "QWEN_MODEL", "qwen-max")
    monkeypatch.setattr(settings, "KIMI_MODEL", "moonshot-v1-8k")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    synthesis_agents: list[str] = []

    async def fake_call(self, config, system_prompt: str, user_prompt: str):
        if "Team responses:" in user_prompt:
            synthesis_agents.append(config.key)
            return "Recommended path\nUse Qwen for breadth, Kimi for long context, and DeepSeek as the extra reviewer."
        return f"{config.label} handled: {user_prompt.splitlines()[1]}"

    monkeypatch.setattr(AgentTeamService, "_call_openai_style", fake_call)

    current_user = TokenPayload(
        sub="platform-admin",
        tenant_id=None,
        client_id=None,
        role=UserRole.PLATFORM_ADMIN,
        permissions=[],
        exp=datetime.now(UTC),
    )

    response = await run_agent_team(
        AgentTeamRunRequest(
            mode="compare",
            task="Design a light agent team orchestrator",
            context="Focus on analysis helpers before code mutation.",
            agents=["qwen", "kimi", "deepseek"],
        ),
        current_user=current_user,
    )

    assert response["mode"] == "compare"
    assert response["agents"] == ["qwen", "kimi", "deepseek"]
    assert len(response["responses"]) == 3
    assert response["responses"][0]["agent"] == "qwen"
    assert response["responses"][1]["agent"] == "kimi"
    assert response["responses"][2]["agent"] == "deepseek"
    assert synthesis_agents == ["qwen"]
    assert "Recommended path" in response["synthesis"]


@pytest.mark.asyncio
async def test_agent_team_run_requires_platform_admin():
    current_user = TokenPayload(
        sub="tenant-admin",
        tenant_id="test-tenant-001",
        client_id=None,
        role=UserRole.TENANT_ADMIN,
        permissions=["master_data.manage"],
        exp=datetime.now(UTC),
    )

    with pytest.raises(HTTPException) as exc:
        await run_agent_team(
            AgentTeamRunRequest(mode="compare", task="Summarize current receiving design"),
            current_user=current_user,
        )

    assert exc.value.status_code == 403
    assert "agent team" in str(exc.value.detail).lower()
