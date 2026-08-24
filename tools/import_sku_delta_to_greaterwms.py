#!/usr/bin/env python3
"""Append the later Delta SKU export through the GreaterWMS API only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from restore_session_to_greaterwms import (
    WmsClient,
    create_or_get_named,
    load_json,
    md5,
    safe_float,
    supplier_name_from_source,
    truncate,
)


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "project" / "dallas peter warehouse" / "session-backup" / "2026-08-07-greaterwms-inputs"


def create_delta_skus(client: WmsClient, records: list[dict], username: str) -> dict:
    result = {"created": [], "updated_existing": [], "skipped_existing": [], "errors": []}
    existing = {record.get("goods_code"): record for record in client.get_all("goods")}
    create_or_get_named(client, "goodsunit", "goods_unit", "Piece", {"goods_unit": "Piece", "creater": username})
    create_or_get_named(client, "goodsbrand", "goods_brand", "Delta", {"goods_brand": "Delta", "creater": username})
    create_or_get_named(client, "goodsorigin", "goods_origin", "US", {"goods_origin": "US", "creater": username})
    supplier_names = {supplier_name_from_source(item) for item in records}
    if len(supplier_names) != 1:
        raise ValueError(f"Delta source contains multiple or missing client values: {sorted(supplier_names)}")
    supplier_name = next(iter(supplier_names))
    create_or_get_named(client, "supplier", "supplier_name", supplier_name, {
        "supplier_name": supplier_name,
        "supplier_city": "Unknown",
        "supplier_address": "Session email input; supplier address not provided",
        "supplier_contact": "Not provided",
        "supplier_manager": username,
        "supplier_level": 1,
        "creater": username,
    })
    for item in records:
        sku = item["sku"]
        if sku in existing:
            current = existing[sku]
            if current.get("goods_supplier") == supplier_name:
                result["skipped_existing"].append(sku)
                continue
            try:
                update_payload = {
                    "goods_code": current["goods_code"],
                    "goods_desc": current["goods_desc"],
                    "goods_supplier": supplier_name,
                    "goods_weight": current["goods_weight"],
                    "goods_w": current["goods_w"],
                    "goods_d": current["goods_d"],
                    "goods_h": current["goods_h"],
                    "unit_volume": current["unit_volume"],
                    "goods_unit": current["goods_unit"],
                    "goods_class": current["goods_class"],
                    "goods_brand": current["goods_brand"],
                    "goods_color": current["goods_color"],
                    "goods_shape": current["goods_shape"],
                    "goods_specs": current["goods_specs"],
                    "goods_origin": current["goods_origin"],
                    "goods_cost": current["goods_cost"],
                    "goods_price": current["goods_price"],
                    "creater": current["creater"],
                    "bar_code": current.get("bar_code"),
                }
                client.request("PATCH", f"goods/{current['id']}", json_data=update_payload)
                result["updated_existing"].append(sku)
            except Exception as exc:
                result["errors"].append({"sku": sku, "error": str(exc)})
            continue
        row = item.get("original_row") or {}
        origin = str(row.get("Origin Country") or "US").strip() or "US"
        if origin not in {"US", "VN"}:
            origin = "US"
        dims = item["dimensions_imperial"]
        try:
            record = client.request("POST", "goods", json_data={
                "goods_code": sku,
                "goods_desc": truncate(" | ".join(filter(None, [item.get("name"), item.get("alternate_sku"), item.get("source_note")]))),
                "goods_supplier": supplier_name,
                "goods_weight": safe_float(item.get("weight_lb")),
                "goods_w": safe_float(dims.get("length")),
                "goods_d": safe_float(dims.get("width")),
                "goods_h": safe_float(dims.get("height")),
                "unit_volume": 0,
                "goods_unit": "Piece",
                "goods_class": "Industrial",
                "goods_brand": "Delta" if str(row.get("Brand") or "").strip() else "Unspecified",
                "goods_color": "N/A",
                "goods_shape": "Crate",
                "goods_specs": "Imperial",
                "goods_origin": origin,
                "goods_cost": safe_float(row.get("Purchasing Cost")),
                "goods_price": safe_float(row.get("Declared Value")),
                "creater": username,
                "bar_code": md5(sku),
            })
            result["created"].append({"sku": sku, "id": record.get("id") if isinstance(record, dict) else None})
            existing[sku] = record
        except Exception as exc:
            result["errors"].append({"sku": sku, "error": str(exc)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WMS_BASE_URL"))
    parser.add_argument("--token", default=os.environ.get("WMS_TOKEN"))
    parser.add_argument("--operator", default=os.environ.get("WMS_OPERATOR", "1"))
    parser.add_argument("--username", default=os.environ.get("WMS_USERNAME", "wuqingxin1978@icloud.com"))
    args = parser.parse_args()
    if not args.base_url or not args.token:
        print("WMS_BASE_URL and WMS_TOKEN are required", file=sys.stderr)
        return 2
    data = load_json("sku-master.json")
    client = WmsClient(args.base_url, args.token, args.operator)
    result = {
        "source_file": "Export Standalone_Items (1) - latest Delta SKU.xlsx",
        "source_record_count": len(data["email_delta"]),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    result.update(create_delta_skus(client, data["email_delta"], args.username))
    result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (BACKUP / "delta-import-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "source_records": result["source_record_count"],
        "created": len(result["created"]),
        "updated_existing": len(result["updated_existing"]),
        "skipped_existing": len(result["skipped_existing"]),
        "errors": len(result["errors"]),
        "result_file": str(BACKUP / "delta-import-result.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
