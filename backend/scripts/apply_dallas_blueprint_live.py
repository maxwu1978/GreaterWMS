"""Apply the Dallas blueprint and WCS point mappings to a persistent WMS tenant.

This is the guarded live/persistent counterpart to
`verify_dallas_blueprint_validate_only.py`.

Required safeguards:
- Set WMS_DALLAS_APPLY_CONFIRM=ALLOW_DALLAS_BLUEPRINT_WRITE to execute the
  warehouse-blueprint confirm.
- Set WMS_DALLAS_IMPORT_CONFIRM=ALLOW_DALLAS_WCS_MAPPING_IMPORT to execute the
  WCS point-mapping import.
- For an existing DAL warehouse, set WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE=true
  to skip duplicate blueprint creation and proceed with WCS validation/import.
- If the existing warehouse still has the known Dallas layout-v2 legacy A-zone
  racks, set WMS_DALLAS_EXISTING_CLEANUP_CONFIRM=
  ALLOW_DALLAS_EXISTING_LAYOUT_CLEANUP to retire those stale storage locations
  before import.
- Provide either WMS_TOKEN or WMS_EMAIL + WMS_PASSWORD.

The script does not log tokens, passwords, or confirmation tokens. It writes
redacted summaries to tmp/dallas-live-apply-<timestamp>/.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_PATH = REPO_ROOT / "exports" / "dallas-local-agent-blueprint-draft.json"
APPLY_CONFIRM = "ALLOW_DALLAS_BLUEPRINT_WRITE"
IMPORT_CONFIRM = "ALLOW_DALLAS_WCS_MAPPING_IMPORT"
EXISTING_CLEANUP_CONFIRM = "ALLOW_DALLAS_EXISTING_LAYOUT_CLEANUP"
LEGACY_A_LAYOUT_V2_BARCODE = re.compile(r"^DAL-A-0[1-4]-0[5-7]-01-01$")


def die(message: str) -> None:
    raise SystemExit(message)


def assert_condition(condition: bool, message: str, details: Any | None = None) -> None:
    if not condition:
        if details is None:
            die(message)
        die(f"{message}: {json.dumps(details, indent=2, sort_keys=True)}")


def api_base() -> str:
    raw = os.getenv("WMS_API_URL", "https://api.maxsmartwms.online").rstrip("/")
    if raw.endswith("/api/v1"):
        return raw[: -len("/api/v1")]
    return raw


def api_v1() -> str:
    return f"{api_base()}/api/v1"


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    request_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc


def login() -> str:
    token = os.getenv("WMS_TOKEN")
    if token:
        return token
    email = os.getenv("WMS_EMAIL")
    password = os.getenv("WMS_PASSWORD")
    assert_condition(bool(email and password), "Set WMS_TOKEN or WMS_EMAIL + WMS_PASSWORD.")
    auth = request_json(
        "POST",
        f"{api_v1()}/auth/login",
        body={"email": email, "password": password},
    )
    token = auth.get("access_token")
    assert_condition(bool(token), "Login response did not include access_token.")
    return str(token)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def redact_preview(preview: dict) -> dict:
    return {
        "ok": preview.get("ok"),
        "dry_run": preview.get("dry_run"),
        "writes": preview.get("writes"),
        "target": preview.get("target"),
        "summary": preview.get("summary"),
        "blocking_errors": preview.get("blocking_errors"),
        "confirmation_required_for_write": preview.get("confirmation_required_for_write"),
        "evidence_id": preview.get("evidence_id"),
        "next_action": preview.get("next_action"),
    }


def role_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = str(row.get("point_role") or row.get("point_type"))
        counts[role] = counts.get(role, 0) + 1
    return counts


def assert_preview_shape(preview: dict) -> None:
    assert_condition(preview.get("writes") is False, "Live blueprint preview must be dry-run.")
    assert_condition(
        preview.get("summary", {}).get("location_count") == 108,
        "Preview location count mismatch.",
        preview.get("summary"),
    )
    assert_condition(
        preview.get("summary", {}).get("wcs_point_mapping_draft_count") == 119,
        "Preview WCS point count mismatch.",
        preview.get("summary"),
    )


def is_existing_duplicate_preview(preview: dict) -> bool:
    target = preview.get("target") or {}
    if target.get("will_create") is not False or not target.get("id"):
        return False
    codes = {str(error.get("code")) for error in preview.get("blocking_errors") or []}
    return {"zone_code_exists", "location_barcode_exists"}.issubset(codes)


def settings_preview_and_confirm(
    *,
    token: str,
    location_id: str,
    changes: dict[str, Any],
    idempotency_key: str,
) -> dict:
    body = {"location_id": location_id, "changes": changes}
    preview = request_json(
        "POST",
        f"{api_v1()}/agent/settings/warehouse-location/preview",
        token=token,
        body=body,
    )
    confirmation_token = (preview.get("confirmation_payload") or {}).get("confirmation_token")
    assert_condition(
        bool(confirmation_token),
        "Location settings preview did not return a confirmation token.",
        preview,
    )
    return request_json(
        "POST",
        f"{api_v1()}/agent/settings/warehouse-location/agent",
        token=token,
        body={**body, "confirmation_token": confirmation_token},
        headers={"X-Idempotency-Key": idempotency_key},
    )


def cleanup_existing_legacy_a_locations(
    *,
    token: str,
    warehouse_id: str,
    validation: dict,
    output_dir: Path,
    stamp: str,
) -> dict:
    unmapped = validation.get("unmapped_agv_locations") or []
    if not unmapped:
        return {"executed": False, "reason": "no_unmapped_agv_locations"}

    legacy = [
        row
        for row in unmapped
        if LEGACY_A_LAYOUT_V2_BARCODE.match(str(row.get("location_barcode") or ""))
    ]
    assert_condition(
        len(legacy) == len(unmapped) == 12,
        "Existing DAL warehouse has unmapped AGV locations outside the known layout-v2 legacy A-zone cleanup set.",
        {"unmapped_agv_locations": unmapped},
    )
    assert_condition(
        os.getenv("WMS_DALLAS_EXISTING_CLEANUP_CONFIRM") == EXISTING_CLEANUP_CONFIRM,
        f"Set WMS_DALLAS_EXISTING_CLEANUP_CONFIRM={EXISTING_CLEANUP_CONFIRM} to retire legacy DAL-A racks.",
    )

    location_updates = []
    for row in legacy:
        barcode = str(row["location_barcode"])
        confirmed = settings_preview_and_confirm(
            token=token,
            location_id=str(row["location_id"]),
            changes={
                "is_agv_accessible": False,
                "current_status": "blocked",
                "wcs_point_metadata": {},
                "layout_metadata": {
                    "dallas_layout_v2_cleanup": True,
                    "reason": "Legacy A-zone column 5-7 is outside the Dallas AGV layout v2 WCS target set.",
                    "source": "dallas-agv-standard-layout-v2",
                    "changed_at": stamp,
                },
            },
            idempotency_key=f"dallas-layout-v2-retire-legacy-a-{barcode}",
        )
        location_updates.append(
            {
                "location_barcode": barcode,
                "location_id": row["location_id"],
                "changed_fields": confirmed.get("changed_fields"),
                "evidence_id": confirmed.get("evidence_id"),
            }
        )

    zones = request_json("GET", f"{api_v1()}/warehouses/{warehouse_id}/zones", token=token)
    dal_a_zone = next((zone for zone in zones if zone.get("code") == "DAL-A"), None)
    assert_condition(bool(dal_a_zone), "DAL-A zone was not found for legacy rack cleanup.", zones)
    rack_pairs = sorted(
        {
            (str(row["location_barcode"]).split("-")[2], str(row["location_barcode"]).split("-")[3])
            for row in legacy
        }
    )
    deleted_racks = []
    for aisle, rack in rack_pairs:
        request_json(
            "DELETE",
            f"{api_v1()}/warehouses/{warehouse_id}/racks",
            token=token,
            body={"zone_id": dal_a_zone["id"], "aisle": aisle, "rack": rack},
        )
        deleted_racks.append({"aisle": aisle, "rack": rack})

    result = {
        "executed": True,
        "retired_location_count": len(location_updates),
        "deleted_rack_count": len(deleted_racks),
        "locations": location_updates,
        "deleted_racks": deleted_racks,
    }
    write_json(output_dir / "existing-legacy-a-cleanup.redacted.json", result)
    return result


def export_point_mapping_summary(token: str, warehouse_id: str) -> dict:
    query = urllib.parse.urlencode(
        {"warehouse_id": warehouse_id, "include_unmapped": "true", "format": "json"}
    )
    exported = request_json(
        "GET",
        f"{api_v1()}/integrations/wcs/point-mappings?{query}",
        token=token,
    )
    items = exported.get("items") or []
    return {
        "warehouse_location_count": len(
            [item for item in items if not item.get("is_external_point")]
        ),
        "mapped_items": len([item for item in items if item.get("point_code")]),
        "agv_mapped_items": len(
            [
                item
                for item in items
                if item.get("point_code") and item.get("wms_agv_accessible") is True
            ]
        ),
        "non_agv_mapped_items": len(
            [
                item
                for item in items
                if item.get("point_code") and item.get("wms_agv_accessible") is False
            ]
        ),
        "external_points": exported.get("external_points"),
        "mapped_locations": exported.get("mapped_locations"),
        "unmapped_locations": exported.get("unmapped_locations"),
    }


def main() -> None:
    assert_condition(BLUEPRINT_PATH.exists(), f"Missing {BLUEPRINT_PATH}")
    assert_condition(
        os.getenv("WMS_DALLAS_APPLY_CONFIRM") == APPLY_CONFIRM,
        f"Set WMS_DALLAS_APPLY_CONFIRM={APPLY_CONFIRM} to execute blueprint confirm.",
    )
    assert_condition(
        os.getenv("WMS_DALLAS_IMPORT_CONFIRM") == IMPORT_CONFIRM,
        f"Set WMS_DALLAS_IMPORT_CONFIRM={IMPORT_CONFIRM} to execute WCS mapping import.",
    )

    stamp = time.strftime("%Y%m%d%H%M%S")
    output_dir = REPO_ROOT / "tmp" / f"dallas-live-apply-{stamp}"
    token = login()
    health = request_json("GET", f"{api_base()}/health")
    expected_sha = os.getenv("WMS_EXPECTED_BUILD_SHA")
    if expected_sha:
        assert_condition(
            health.get("build_sha") == expected_sha,
            "Production health build_sha does not match expected deployment.",
            {"expected": expected_sha, "actual": health.get("build_sha")},
        )
    write_json(output_dir / "health.json", {"status": health.get("status"), "build_sha": health.get("build_sha")})

    blueprint = json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    assert_condition(blueprint.get("warehouse", {}).get("code") == "DAL", "Blueprint warehouse code must be DAL.")
    preview = request_json("POST", f"{api_v1()}/agent/warehouse-blueprints/preview", token=token, body=blueprint)
    write_json(output_dir / "blueprint-preview.redacted.json", redact_preview(preview))
    assert_preview_shape(preview)
    existing_mode = is_existing_duplicate_preview(preview)
    if preview.get("ok") is True:
        assert_condition(
            preview.get("confirmation_payload", {}).get("confirmation_token"),
            "Preview did not return a confirmation token.",
        )
        confirm_body = {**blueprint, "confirmation_token": preview["confirmation_payload"]["confirmation_token"]}
        idempotency_key = os.getenv("WMS_DALLAS_BLUEPRINT_IDEMPOTENCY_KEY", f"dallas-blueprint-confirm-{stamp}")
        confirmed = request_json(
            "POST",
            f"{api_v1()}/agent/warehouse-blueprints/agent",
            token=token,
            body=confirm_body,
            headers={"X-Idempotency-Key": idempotency_key},
        )
        warehouse = confirmed.get("warehouse") or {}
        warehouse_id = warehouse.get("id") or confirmed.get("entity", {}).get("id")
        blueprint_result = {
            "mode": "created",
            "warehouse": warehouse,
            "created_zone_ids": confirmed.get("created_zone_ids"),
            "created_location_count": confirmed.get("created_location_count"),
            "evidence_id": confirmed.get("evidence_id"),
            "idempotency_key": confirmed.get("idempotency_key"),
            "next_action": confirmed.get("next_action"),
        }
        write_json(output_dir / "blueprint-confirm.redacted.json", blueprint_result)
        assert_condition(bool(warehouse_id), "Blueprint confirm did not return a warehouse id.", confirmed)
        assert_condition(
            confirmed.get("created_location_count") == 108,
            "Blueprint confirm location count mismatch.",
            confirmed,
        )
    elif existing_mode:
        assert_condition(
            os.getenv("WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE") == "true",
            "Live preview targets an existing DAL warehouse. Set WMS_DALLAS_ALLOW_EXISTING_WAREHOUSE=true after reviewing the preview.",
        )
        warehouse = preview.get("target") or {}
        warehouse_id = warehouse.get("id")
        blueprint_result = {
            "mode": "existing_warehouse_reused",
            "warehouse": warehouse,
            "created_zone_ids": [],
            "created_location_count": 0,
            "blocking_errors": preview.get("blocking_errors"),
            "next_action": "validate_and_import_wcs_mappings_for_existing_warehouse",
        }
        write_json(output_dir / "blueprint-existing.redacted.json", blueprint_result)
    else:
        assert_condition(False, "Live blueprint preview failed.", preview.get("blocking_errors"))

    mappings = preview.get("wcs_point_mapping_draft") or []
    assert_condition(len(mappings) == 119, "Expected 119 WCS mappings from live preview.")
    validation = request_json(
        "POST",
        f"{api_v1()}/integrations/wcs/point-mappings/validate",
        token=token,
        body={"warehouse_id": warehouse_id, "mappings": mappings},
    )
    write_json(output_dir / "point-mappings-validate.json", validation)
    assert_condition(validation.get("ok") is True, "WCS point mapping validation failed.", validation.get("issues"))
    assert_condition(validation.get("summary", {}).get("mapped_locations") == 108, "WCS mapped location count mismatch.")
    cleanup_result = {"executed": False, "reason": "not_needed"}
    if validation.get("summary", {}).get("unmapped_agv_accessible_locations"):
        assert_condition(
            existing_mode,
            "WCS validation found unmapped AGV locations for a newly created warehouse.",
            validation,
        )
        cleanup_result = cleanup_existing_legacy_a_locations(
            token=token,
            warehouse_id=str(warehouse_id),
            validation=validation,
            output_dir=output_dir,
            stamp=stamp,
        )
        validation = request_json(
            "POST",
            f"{api_v1()}/integrations/wcs/point-mappings/validate",
            token=token,
            body={"warehouse_id": warehouse_id, "mappings": mappings},
        )
        write_json(output_dir / "point-mappings-validate-after-cleanup.json", validation)
        assert_condition(validation.get("ok") is True, "WCS point mapping validation after cleanup failed.", validation.get("issues"))
        assert_condition(validation.get("summary", {}).get("mapped_locations") == 108, "WCS mapped location count mismatch after cleanup.")
    assert_condition(
        validation.get("summary", {}).get("unmapped_agv_accessible_locations") == 0,
        "WCS validation found unmapped AGV locations.",
        validation,
    )

    imported = request_json(
        "POST",
        f"{api_v1()}/integrations/wcs/point-mappings/import",
        token=token,
        body={
            "warehouse_id": warehouse_id,
            "mappings": mappings,
            "merge": os.getenv("WMS_DALLAS_MAPPING_MERGE", "false").lower() == "true",
            "validate_only": False,
        },
    )
    write_json(output_dir / "point-mappings-import.json", imported)
    assert_condition(
        imported.get("ok") is True or imported.get("status") == "configured",
        "WCS point mapping import did not report success.",
        imported,
    )

    final_validation = request_json(
        "POST",
        f"{api_v1()}/integrations/wcs/point-mappings/validate",
        token=token,
        body={"warehouse_id": warehouse_id, "mappings": mappings},
    )
    assert_condition(final_validation.get("ok") is True, "Final WCS validation failed.", final_validation)
    assert_condition(
        final_validation.get("summary", {}).get("unmapped_agv_accessible_locations") == 0,
        "Final WCS validation found unmapped AGV locations.",
        final_validation,
    )
    export_summary = export_point_mapping_summary(token, str(warehouse_id))
    assert_condition(export_summary.get("warehouse_location_count") == 108, "Final warehouse location count mismatch.", export_summary)
    assert_condition(export_summary.get("agv_mapped_items") == 108, "Final AGV mapped item count mismatch.", export_summary)
    assert_condition(export_summary.get("external_points") == 11, "Final external WCS point count mismatch.", export_summary)
    assert_condition(export_summary.get("non_agv_mapped_items") == 0, "Final export contains non-AGV mapped items.", export_summary)
    assert_condition(export_summary.get("unmapped_locations") == 0, "Final export contains unmapped locations.", export_summary)
    summary = {
        "ok": True,
        "api_base": api_base(),
        "health": {"status": health.get("status"), "build_sha": health.get("build_sha")},
        "warehouse": warehouse,
        "blueprint": blueprint_result,
        "existing_cleanup": cleanup_result,
        "wcs": {
            "import_status": imported.get("status"),
            "mapping_count": len(mappings),
            "role_counts": role_counts(mappings),
            "validation_summary": final_validation.get("summary"),
            "export_summary": export_summary,
        },
        "artifacts_dir": str(output_dir),
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - script should return a clear operational failure.
        print(str(exc), file=sys.stderr)
        raise
