from pathlib import Path


def read_static_html() -> str:
    return (
        Path(__file__).resolve().parents[1] / "local_agent" / "static" / "index.html"
    ).read_text(encoding="utf-8")


def test_settings_panel_has_structured_preview_controls() -> None:
    html = read_static_html()

    for expected in [
        'id="settingsCategory"',
        'id="settingsEntityId"',
        'id="settingsChangesJson"',
        'id="settingsSimpleControls"',
        'id="receivingCodeControls"',
        'id="receivingCodePrefix"',
        'id="receivingCodePadding"',
        'id="receivingLabelControls"',
        'id="receivingLabelFields"',
        'id="clientProfileControls"',
        'id="clientProfileEmail"',
        'id="clientProfilePhone"',
        'id="skuControls"',
        'id="skuName"',
        'id="skuBarcode"',
        'id="warehouseLocationControls"',
        'id="warehouseLocationStatus"',
        'id="warehouseLocationType"',
        "Advanced JSON",
        "updateAdvancedJsonFromSimpleSettings",
        'id="settingsPreviewBtn"',
        'id="settingsDiff"',
        'id="settingsResult"',
        "settings.receiving_codes.preview",
        "settings.client_profile.preview",
        "settings.billing_rate_card.preview",
        "latestIdempotencyKey",
    ]:
        assert expected in html

    assert "previewCodesBtn" not in html
    assert "previewLabelsBtn" not in html


def test_evidence_detail_ui_uses_session_scoped_lookup_without_tokens() -> None:
    html = read_static_html()

    for expected in [
        'id="evidenceLookup"',
        'id="auditBtn">Activity log</button>',
        'id="evidenceIdInput"',
        'id="viewEvidenceBtn"',
        'id="replayPreviewBtn"',
        'id="failedEvidenceBtn"',
        'id="evidencePanel"',
        "View evidence",
        "Replay preview",
        "Failed evidence",
        "failedEvidenceFilter",
        "data-copy-value",
        "Copy ID",
        "Impact",
        "Strong confirmation",
        "Before",
        "After",
        "What happened: preview is ready.",
        "What to do next: confirm this write or cancel and rerun preview.",
        ".confirm-grid,",
        ".settings-simple-grid",
        "strongConfirmationInput",
        "strong_confirmation_required",
        "strong_confirmation:",
        "evidenceIdFromValue",
        "evidenceButton(card.evidence_id)",
        "evidenceButton(preview.evidence_id)",
        "evidenceButton(result.evidence_id)",
        "/api/evidence/${encodeURIComponent(id)}?session_id=${encodeURIComponent(state.sessionId)}",
        "/api/evidence/${encodeURIComponent(id)}/replay-preview?session_id=${encodeURIComponent(state.sessionId)}",
        "/api/evidence/failed?session_id=${encodeURIComponent(state.sessionId)}",
        "loadEvidenceReplayPreview",
        "loadFailedEvidenceList",
        "renderFailedEvidencePanel",
        "safeEvidenceValue",
        "isSensitiveKey",
        "token|password|secret|api[_-]?key|authorization|credential",
    ]:
        assert expected in html

    assert "renderOutput(payload);" not in html[
        html.index("async function loadEvidenceDetail") : html.index("function renderConfirmation")
    ]
    assert "confirmation_token" not in html[
        html.index("function renderConfirmation") : html.index("async function confirmLatest")
    ]


def test_planner_comparison_ui_is_local_only() -> None:
    html = read_static_html()

    for expected in [
        'id="compareBtn"',
        "Compare planners",
        "/api/plans/compare",
        "Planner comparison failed",
    ]:
        assert expected in html


def test_quick_actions_are_grouped_by_operator_intent() -> None:
    html = read_static_html()

    for expected in [
        'class="quick-groups"',
        "Daily work",
        "Master data",
        "Admin and setup",
        'id="mapBtn"',
        'id="blueprintBtn"',
        "Show inventory on hand",
        "Show billing setup",
    ]:
        assert expected in html


def test_warehouse_map_engine_uses_governed_read_tools() -> None:
    html = read_static_html()

    for expected in [
        'id="mapBtn"',
        "Warehouse map",
        'id="warehouseMapCanvas"',
        'id="warehouseMapSelect"',
        'id="refreshMapBtn"',
        'id="warehouseMapZoomOutBtn"',
        'id="warehouseMapZoomInBtn"',
        'id="warehouseMapResetViewBtn"',
        'id="warehouseMapFullscreenBtn"',
        'id="warehouseMapInspector"',
        "function drawWarehouseMap",
        "function loadWarehouseMap",
        "setWarehouseMapZoom",
        "resetWarehouseMapView",
        "startWarehouseMapPan",
        "toggleCanvasFullscreen",
        "canvas-fullscreen",
        "settings.warehouse_locations.list",
        "warehouses.list",
        "locationStatusColor",
        "mapLocationAtEvent",
        "mapLocationLayout",
        "slot_layout_percent",
        "layout_percent",
        "{ limit: 500 }",
    ]:
        assert expected in html

    assert "DELETE" not in html[
        html.index("async function loadWarehouseMap") : html.index("function renderConfirmation")
    ]


def test_blueprint_draft_engine_supports_upload_parse_review_and_copy() -> None:
    html = read_static_html()

    for expected in [
        'id="blueprintBtn"',
        'id="blueprintPanel"',
        'id="blueprintFile"',
        'id="blueprintDescription"',
        'id="generateBlueprintBtn"',
        'id="blueprintCanvas"',
        'id="blueprintDetail"',
        'id="copyBlueprintBtn"',
        'id="blueprintZoomOutBtn"',
        'id="blueprintZoomInBtn"',
        'id="blueprintResetViewBtn"',
        'id="blueprintFullscreenBtn"',
        "parseBlueprintDescription",
        "structuredLines",
        "generateDraftLocations",
        "`${zone.code}-${aisleCode}-${rackCode}-${levelCode}-${positionCode}`",
        "drawBlueprint",
        "setBlueprintZoom",
        "resetBlueprintView",
        "requestFullscreen",
        "fullscreenchange",
        "toggleCanvasFullscreen",
        "canvas-fullscreen",
        "startBlueprintPan",
        "blueprintZoneAtEvent",
        "blueprintDraftPayload",
        "zones.find((zone) => !isBlueprintAccessPoint(zone))",
        "blueprintZonePayload",
        "blueprintWcsMappingDraft",
        "wcs_point_mapping_draft",
        "point_type",
        "point_role",
        "virtual",
        "warehouse.blueprint_draft",
        "warehouse.blueprint.preview",
        "blueprintMetadata",
        "blueprintDimensions",
        "validateBlueprintZone",
        "expected_pcs",
        "pallet",
        "height_ft",
        "dimensions",
            "GMA pallet",
            "rows=4 columns=4",
            "A-CONN",
            "104x55x98in",
        "slot_layout_percent",
        "blueprintLocationLayout",
        "review before import",
        "N-WAIT-TOP",
        "N-WAIT-DOCK",
    ]:
        assert expected in html

    blueprint_slice = html[
        html.index("function showBlueprintPanel") : html.index("function evidenceIdFromValue")
    ]
    assert "fetch(" not in blueprint_slice
