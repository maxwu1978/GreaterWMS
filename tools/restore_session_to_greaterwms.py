#!/usr/bin/env python3
"""Restore the session recovery package through the GreaterWMS HTTP API.

The script deliberately uses the product API only. It does not import a
database dump and it never writes the authentication token to the backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "project" / "dallas peter warehouse" / "session-backup" / "2026-08-07-greaterwms-inputs"

# These four records were added from the Delta scan sheet/photos rather than a
# row containing a customer name. Keep the source-derived mapping explicit so
# a missing customer field can never silently fall back to another supplier.
SOURCE_DERIVED_CLIENT_OVERRIDES = {
    "CLSCU-AA401-S": "Delta Electronics (USA) Inc.(56315)",
    "CLSCAC144AD702": "Delta Electronics (USA) Inc.(56315)",
    "702-S": "Delta Electronics (USA) Inc.(56315)",
    "401-S": "Delta Electronics (USA) Inc.(56315)",
}


class ApiError(RuntimeError):
    pass


class WmsClient:
    def __init__(self, base_url: str, token: str, operator: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"token": token, "operator": operator, "Accept": "application/json"})

    def url(self, path: str) -> str:
        return self.base_url + "/" + path.strip("/") + "/"

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json_data: dict[str, Any] | None = None, tries: int = 4) -> Any:
        url = path if path.startswith("http") else self.url(path)
        last_error: Exception | None = None
        for attempt in range(tries):
            try:
                response = self.session.request(method, url, params=params, json=json_data, timeout=(20, 120))
                if response.status_code in (502, 503, 504, 429):
                    time.sleep(2 + attempt * 2)
                    continue
                try:
                    data = response.json()
                except ValueError:
                    data = response.text[:1000]
                if response.status_code >= 400:
                    raise ApiError(f"{method} {url} -> {response.status_code}: {data}")
                return data
            except (requests.RequestException, ApiError) as exc:
                last_error = exc
                if attempt + 1 < tries:
                    time.sleep(2 + attempt * 2)
        raise ApiError(str(last_error))

    def get_all(self, path: str) -> list[dict[str, Any]]:
        first = self.request("GET", path)
        if not isinstance(first, dict):
            return first if isinstance(first, list) else []
        records = list(first.get("results") or first.get("data") or [])
        next_url = first.get("next")
        while next_url:
            parsed = urlparse(next_url)
            query = parse_qs(parsed.query)
            page = query.get("page", [None])[0]
            params = {"page": page} if page else None
            page_data = self.request("GET", path, params=params)
            if not isinstance(page_data, dict):
                break
            records.extend(page_data.get("results") or page_data.get("data") or [])
            next_url = page_data.get("next")
        return records


def load_json(name: str) -> Any:
    return json.loads((BACKUP / name).read_text(encoding="utf-8"))


def md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def truncate(value: str, limit: int = 255) -> str:
    return str(value or "")[:limit] or "Imported session record"


def supplier_name_from_source(item: dict[str, Any]) -> str:
    """Resolve supplier from the source customer/owner, never a global default."""
    original_row = item.get("original_row") or {}
    client = str(original_row.get("Client") or item.get("client") or "").strip()
    if client == "Session supplemental input":
        client = SOURCE_DERIVED_CLIENT_OVERRIDES.get(str(item.get("sku") or ""), "")
    if not client:
        raise ApiError(f"Missing source client/owner for SKU {item.get('sku')}")
    return client


def supplier_map_from_source(all_skus: list[dict[str, Any]]) -> dict[str, str]:
    return {str(item["sku"]): supplier_name_from_source(item) for item in all_skus}


def clean_resource(client: WmsClient, path: str, *, keep_ids: set[int] | None = None) -> dict[str, Any]:
    records = client.get_all(path)
    deleted = 0
    errors = []
    for record in records:
        record_id = record.get("id")
        if record_id is None or int(record_id) in (keep_ids or set()):
            continue
        try:
            client.request("DELETE", f"{path}/{record_id}")
            deleted += 1
        except Exception as exc:  # Keep going and report every failed row.
            errors.append({"id": record_id, "error": str(exc)})
    return {"found": len(records), "deleted": deleted, "errors": errors}


def create_or_get_named(client: WmsClient, path: str, field: str, value: str, payload: dict[str, Any]) -> dict[str, Any]:
    records = client.get_all(path)
    for record in records:
        if record.get(field) == value:
            return record
    return client.request("POST", path, json_data=payload)


def clean_demo_data(client: WmsClient, admin_id: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    # Remove dependent operational data first if a previous partial restore exists.
    for path in ("asn/list", "dn/list"):
        result[path] = clean_resource(client, path)
    for path in ("goods", "supplier", "customer", "driver", "capital", "payment/freight"):
        result[path] = clean_resource(client, path)
    for path in ("goodsunit", "goodsclass", "goodsbrand", "goodscolor", "goodsshape", "goodsspecs", "goodsorigin"):
        result[path] = clean_resource(client, path)
    result["binset"] = clean_resource(client, "binset")
    result["warehouse"] = clean_resource(client, "warehouse")
    result["company"] = clean_resource(client, "company")
    result["staff"] = clean_resource(client, "staff", keep_ids={admin_id})
    return result


def restore_master_data(client: WmsClient, username: str, layout: dict[str, Any], all_skus: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"created": {}, "errors": []}
    company = client.request("POST", "company", json_data={
        "company_name": "Peak Demo Warehouse Operations",
        "company_city": "Dallas",
        "company_address": "Dallas, Texas, United States",
        "company_contact": "Not provided",
        "company_manager": username,
        "creater": username,
    })
    result["created"]["company"] = company.get("id") if isinstance(company, dict) else None
    warehouse = client.request("POST", "warehouse", json_data={
        "warehouse_name": layout["warehouse_name"],
        "warehouse_city": "Dallas",
        "warehouse_address": "Dallas, Texas, United States",
        "warehouse_contact": "Not provided",
        "warehouse_manager": username,
        "creater": username,
    })
    result["created"]["warehouse"] = warehouse.get("id") if isinstance(warehouse, dict) else None

    for path, field, value, payload in (
        ("goodsunit", "goods_unit", "Pallet", {"goods_unit": "Pallet", "creater": username}),
        ("goodsclass", "goods_class", "Industrial", {"goods_class": "Industrial", "creater": username}),
        ("goodsbrand", "goods_brand", "Unspecified", {"goods_brand": "Unspecified", "creater": username}),
        ("goodscolor", "goods_color", "N/A", {"goods_color": "N/A", "creater": username}),
        ("goodsshape", "goods_shape", "Crate", {"goods_shape": "Crate", "creater": username}),
        ("goodsspecs", "goods_specs", "Imperial", {"goods_specs": "Imperial", "creater": username}),
        ("goodsorigin", "goods_origin", "Unknown", {"goods_origin": "Unknown", "creater": username}),
        ("goodsorigin", "goods_origin", "VN", {"goods_origin": "VN", "creater": username}),
    ):
        record = create_or_get_named(client, path, field, value, payload)
        result["created"].setdefault(path, []).append(record.get("id") if isinstance(record, dict) else None)

    for bin_size, width, depth, height in (
        ("Big", 1100, 1200, 1800),
        ("Floor", 10000, 10000, 10000),
        ("Small", 800, 1000, 1200),
        ("Tiny", 200, 250, 300),
    ):
        record = create_or_get_named(
            client,
            "binsize",
            "bin_size",
            bin_size,
            {
                "bin_size": bin_size,
                "bin_size_w": width,
                "bin_size_d": depth,
                "bin_size_h": height,
                "creater": username,
            },
        )
        result["created"].setdefault("binsize", []).append(
            record.get("id") if isinstance(record, dict) else None
        )

    supplier_records = {}
    for supplier_name in sorted({supplier_name_from_source(item) for item in all_skus}):
        supplier_records[supplier_name] = create_or_get_named(
            client,
            "supplier",
            "supplier_name",
            supplier_name,
            {
                "supplier_name": supplier_name,
                "supplier_city": "Unknown",
                "supplier_address": "Source file did not provide an address",
                "supplier_contact": "Not provided",
                "supplier_manager": username,
                "supplier_level": 1,
                "creater": username,
            },
        )
    result["created"]["supplier"] = {
        name: record.get("id") if isinstance(record, dict) else None
        for name, record in supplier_records.items()
    }

    for location in layout["locations"]:
        property_name = "Inspection" if location["type"] == "staging" else "Normal"
        try:
            record = client.request("POST", "binset", json_data={
                "bin_name": location["name"],
                "bin_size": "Big" if location["type"] == "staging" else "Floor",
                "bin_property": property_name,
                "bar_code": md5(location["name"]),
                "creater": username,
            })
            result["created"].setdefault("binset", []).append(record.get("id") if isinstance(record, dict) else None)
        except Exception as exc:
            result["errors"].append({"resource": "binset", "name": location["name"], "error": str(exc)})

    for index, item in enumerate(all_skus, start=1):
        origin = (item.get("original_row") or {}).get("Origin Country") or "Unknown"
        origin = str(origin).strip() or "Unknown"
        dims = item["dimensions_imperial"]
        source_note = item.get("source_note", "")
        description = truncate(" | ".join(filter(None, [item.get("name"), item.get("alternate_sku"), source_note])))
        try:
            record = client.request("POST", "goods", json_data={
                "goods_code": item["sku"],
                "goods_desc": description,
                "goods_supplier": supplier_name_from_source(item),
                "goods_weight": safe_float(item.get("weight_lb")),
                "goods_w": safe_float(dims.get("length")),
                "goods_d": safe_float(dims.get("width")),
                "goods_h": safe_float(dims.get("height")),
                "unit_volume": 0,
                "goods_unit": "Pallet",
                "goods_class": "Industrial",
                "goods_brand": "Unspecified",
                "goods_color": "N/A",
                "goods_shape": "Crate",
                "goods_specs": "Imperial",
                "goods_origin": origin if origin in ("VN", "Unknown") else "Unknown",
                "goods_cost": safe_float((item.get("original_row") or {}).get("Purchasing Cost")),
                "goods_price": safe_float((item.get("original_row") or {}).get("Declared Value")),
                "creater": username,
                "bar_code": md5(item["sku"]),
            })
            result["created"].setdefault("goods", []).append({"source_index": index, "sku": item["sku"], "id": record.get("id") if isinstance(record, dict) else None})
        except Exception as exc:
            result["errors"].append({"resource": "goods", "sku": item["sku"], "error": str(exc)})
    return result


def restore_asn_and_serials(
    client: WmsClient,
    username: str,
    scan: dict[str, Any],
    source_filename: str,
    supplier_by_sku: dict[str, str],
) -> dict[str, Any]:
    result: dict[str, Any] = {"asn": [], "errors": []}
    for source in scan["inbound_summary"]:
        source_po = source["source_inbound_po"]
        try:
            goods_codes = list(source["sku_quantities"].keys())
            supplier_names = {supplier_by_sku.get(code) for code in goods_codes}
            if None in supplier_names or len(supplier_names) != 1:
                raise ApiError(
                    f"ASN {source_po} has missing or mixed source suppliers: {sorted(supplier_names)}"
                )
            supplier_name = next(iter(supplier_names))
            asn = client.request("POST", "asn/list", json_data={
                "asn_code": "ASN00000001",
                "supplier": supplier_name,
                "creater": username,
                "bar_code": md5(source_po),
            })
            asn_code = asn.get("asn_code") if isinstance(asn, dict) else None
            if not asn_code:
                raise ApiError(f"ASN create returned no asn_code: {asn}")
            quantities = [int(source["sku_quantities"][code]) for code in goods_codes]
            detail = client.request("POST", "asn/detail", json_data={
                "asn_code": asn_code,
                "supplier": supplier_name,
                "goods_code": goods_codes,
                "goods_qty": quantities,
                "creater": username,
            })
            expected_rows = []
            for row in scan["inbound_rows"]:
                if row["inbound_po"] != source_po:
                    continue
                expected_rows.append({
                    "serial_number": row["sn"],
                    "goods_code": row["sku"],
                    "double_scan_sn": row["double_scan_sn"],
                    "inbound_po": row["inbound_po"],
                    "inbound_date": row["inbound_date"],
                    "source_location": row["location"],
                    "shipout_ref": row["shipout_ref"],
                    "source_file": source_filename,
                    "source_row": row["source_row"],
                })
            expected = client.request("POST", "asn/serial/expected", json_data={"asn_code": asn_code, "rows": expected_rows})
            received = 0
            receive_errors = []
            for row in expected_rows:
                try:
                    client.request("POST", "asn/serial/scan", json_data={
                        "asn_code": asn_code,
                        "goods_code": row["goods_code"],
                        "serial_number": row["serial_number"],
                        **{key: row[key] for key in ("double_scan_sn", "inbound_po", "inbound_date", "source_location", "shipout_ref", "source_file", "source_row")},
                    })
                    received += 1
                except Exception as exc:
                    receive_errors.append({"sn": row["serial_number"], "error": str(exc)})
            result["asn"].append({
                "source_inbound_po": source_po,
                "system_asn_code": asn_code,
                "source_rows": source["source_rows"],
                "expected_count": len(expected_rows),
                "received_count": received,
                "receive_errors": receive_errors,
                "detail_response": detail,
                "expected_response": expected,
            })
        except Exception as exc:
            result["errors"].append({"source_inbound_po": source_po, "error": str(exc)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("WMS_BASE_URL"))
    parser.add_argument("--token", default=os.environ.get("WMS_TOKEN"))
    parser.add_argument("--operator", default=os.environ.get("WMS_OPERATOR", "1"))
    parser.add_argument("--username", default=os.environ.get("WMS_USERNAME", "wuqingxin1978@icloud.com"))
    parser.add_argument("--skip-clean", action="store_true")
    args = parser.parse_args()
    if not args.base_url or not args.token:
        print("WMS_BASE_URL and WMS_TOKEN are required", file=sys.stderr)
        return 2

    layout = load_json("warehouse-layout.json")
    sku_data = load_json("sku-master.json")
    scan = load_json("inbound-scan-history.json")
    supplier_by_sku = supplier_map_from_source(sku_data["all_records"])
    client = WmsClient(args.base_url, args.token, args.operator)
    result: dict[str, Any] = {
        "base_url": args.base_url,
        "backup_dir": str(BACKUP),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "clean": None,
        "master_data": None,
        "asn_serials": None,
    }
    if not args.skip_clean:
        result["clean"] = clean_demo_data(client, int(args.operator))
    result["master_data"] = restore_master_data(client, args.username, layout, sku_data["all_records"])
    result["asn_serials"] = restore_asn_and_serials(
        client,
        args.username,
        scan,
        scan["source_file"],
        supplier_by_sku,
    )
    result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (BACKUP / "restore-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "clean_errors": sum(len(item.get("errors", [])) for item in (result["clean"] or {}).values()),
        "master_errors": len((result["master_data"] or {}).get("errors", [])),
        "asn_errors": len((result["asn_serials"] or {}).get("errors", [])),
        "asn_count": len((result["asn_serials"] or {}).get("asn", [])),
        "received_sn": sum(item.get("received_count", 0) for item in (result["asn_serials"] or {}).get("asn", [])),
        "result_file": str(BACKUP / "restore-result.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not any(summary[key] for key in ("clean_errors", "master_errors", "asn_errors")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
