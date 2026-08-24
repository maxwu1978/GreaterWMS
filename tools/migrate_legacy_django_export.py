#!/usr/bin/env python3
"""Build a safe SQL migration plan from a legacy GreaterWMS API export.

The legacy Django service remains the source of truth. This tool never reads or
writes the legacy database. It converts an API export into a deterministic,
transactional SQL file for the new WMS database and validates the mapping first.

Typical usage:
    python tools/migrate_legacy_django_export.py \
        --input /private/tmp/greaterwms-production-export-20260825.json \
        --plan /private/tmp/greaterwms-migration-plan.json \
        --sql /private/tmp/greaterwms-migration.sql

The generated SQL uses stable UUIDs and INSERT-only semantics. Re-running it is
idempotent for the same export; a conflicting business key aborts the
transaction instead of overwriting an existing target record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NAMESPACE = uuid.UUID("d75f5e90-5d5e-4e03-b7db-0a3c5f66bda1")
TENANT_CODE = "PEAKSMART"
TENANT_NAME = "Peak Smart Logistics"


def stable_id(kind: str, value: Any) -> str:
    return str(uuid.uuid5(NAMESPACE, f"legacy:{kind}:{value}"))


def parse_datetime(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip().replace(" ", "T", 1)
    if raw.endswith("Z"):
        return raw
    if "+" not in raw[10:] and "-" not in raw[10:]:
        raw += "+00:00"
    return raw


def json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    return cleaned[:50] or "LEGACY"


def extract_code(name: str, fallback: str) -> str:
    match = re.search(r"\((\d{3,})\)", name)
    return match.group(1) if match else fallback


def extract_phone(value: Any) -> str | None:
    if not value:
        return None
    match = re.search(r"\+?\d[\d ()-]{7,}\d", str(value))
    if not match:
        return None
    phone = re.sub(r"(?<=\d) (?=\d)", "", match.group(0)).strip()
    return phone[:20]


def normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def sql_literal(value: Any, cast: str | None = None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    escaped = str(value).replace("'", "''")
    result = f"'{escaped}'"
    return f"{result}::{cast}" if cast else result


def json_sql(value: Any) -> str:
    return sql_literal(json.dumps(value, ensure_ascii=False, separators=(",", ":")), "jsonb")


def dt_or_now(value: Any) -> str:
    return parse_datetime(value) or datetime.now(timezone.utc).isoformat()


def source_resources(export: dict[str, Any]) -> dict[str, Any]:
    resources = export.get("resources")
    if not isinstance(resources, dict):
        raise ValueError("export.resources must be an object")
    return resources


def rows(resources: dict[str, Any], name: str) -> list[dict[str, Any]]:
    resource = resources.get(name, {})
    data = resource.get("data", {}) if isinstance(resource, dict) else {}
    values = data.get("results", []) if isinstance(data, dict) else data
    if not isinstance(values, list):
        raise ValueError(f"resource {name} has no results list")
    return [row for row in values if isinstance(row, dict)]


def build_plan(export: dict[str, Any]) -> dict[str, Any]:
    resources = source_resources(export)
    warehouse_rows = rows(resources, "warehouse")
    customer_rows = rows(resources, "customers")
    supplier_rows = rows(resources, "suppliers")
    goods_rows = rows(resources, "goods")
    bin_rows = rows(resources, "bins")
    asn_rows = rows(resources, "asn")
    source_rows = rows(resources, "source_evidence")

    if len(warehouse_rows) != 1:
        raise ValueError(f"expected exactly one source warehouse, got {len(warehouse_rows)}")
    if len({row.get("goods_code") for row in goods_rows}) != len(goods_rows):
        raise ValueError("duplicate goods_code values found in source export")
    if len({row.get("bin_name") for row in bin_rows}) != len(bin_rows):
        raise ValueError("duplicate bin_name values found in source export")

    source_warehouse = warehouse_rows[0]
    tenant_id = stable_id("tenant", TENANT_CODE)
    warehouse_id = stable_id("warehouse", source_warehouse.get("id", TENANT_NAME))

    # Build a hint index from SKU source metadata before reading the legacy
    # customer master. The legacy customer endpoint may omit the numeric client
    # code while the SKU export contains it, which otherwise creates duplicate
    # Delta client rows.
    client_hints: list[tuple[str, str]] = []
    for goods in goods_rows:
        note = json_object(goods.get("source_note"))
        client_id = str(note.get("client_id") or "").strip()
        client_name = str(note.get("client_name") or "").strip()
        if client_id and client_name and (client_id, client_name) not in client_hints:
            client_hints.append((client_id, client_name))

    client_by_code: dict[str, dict[str, Any]] = {}
    for customer in customer_rows:
        name = str(customer.get("customer_name") or "Unknown client")
        code = extract_code(name, slug(name)[:50])
        if code == slug(name)[:50]:
            matching_hints = [
                hint_code
                for hint_code, hint_name in client_hints
                if normalized_name(name) in normalized_name(hint_name)
                or normalized_name(hint_name) in normalized_name(name)
            ]
            if len(matching_hints) == 1:
                code = matching_hints[0]
        client_by_code[code] = {
            "id": stable_id("client", code),
            "code": code,
            "name": name,
            "contact_email": None,
            "contact_phone": extract_phone(customer.get("customer_contact")),
            "address": {
                "city": customer.get("customer_city") or None,
                "street": customer.get("customer_address") or None,
                "contact": customer.get("customer_manager") or None,
            },
            "source": "legacy customer",
        }

    # Some legacy SKUs belong to clients that were present only in the source
    # spreadsheet, not in the customer master list. Preserve those clients
    # explicitly rather than assigning SKUs to the warehouse operator.
    for goods in goods_rows:
        note = json_object(goods.get("source_note"))
        client_name = str(note.get("client_name") or "").strip()
        client_id = str(note.get("client_id") or "").strip()
        if client_id and client_id not in client_by_code:
            client_by_code[client_id] = {
                "id": stable_id("client", client_id),
                "code": client_id,
                "name": client_name or f"Legacy Client {client_id}",
                "contact_email": None,
                "contact_phone": None,
                "address": None,
                "source": "legacy SKU source metadata",
            }

    if not client_by_code:
        raise ValueError("no client could be mapped from the source export")

    clients = list(client_by_code.values())
    client_ids = set(client_by_code)
    skus: list[dict[str, Any]] = []
    for goods in goods_rows:
        note = json_object(goods.get("source_note"))
        client_code = str(note.get("client_id") or "").strip()
        if client_code not in client_ids:
            raise ValueError(f"SKU {goods.get('goods_code')} has no client mapping")
        dimensions = note.get("normalized_dimensions_in")
        if not isinstance(dimensions, list) or len(dimensions) != 3:
            dimensions = [goods.get("goods_w"), goods.get("goods_d"), goods.get("goods_h")]
        length_in, width_in, height_in = (numeric(item) for item in dimensions)
        weight_lb = numeric(goods.get("goods_weight"))
        skus.append(
            {
                "id": stable_id("sku", goods.get("id", goods.get("goods_code"))),
                "client_code": client_code,
                "sku_code": str(goods.get("goods_code") or "").strip(),
                "barcode": None,
                "name": str(goods.get("goods_desc") or goods.get("goods_code") or "Unnamed SKU"),
                "description": "Migrated from legacy GreaterWMS; source values retained in attributes.",
                "weight_kg": round(weight_lb * 0.45359237, 3),
                "length_cm": round(length_in * 2.54, 2),
                "width_cm": round(width_in * 2.54, 2),
                "height_cm": round(height_in * 2.54, 2),
                "requires_lot": False,
                "requires_expiry": False,
                "is_hazmat": str(note.get("hazardous_battery", "N")).upper() == "Y",
                "units_per_case": integer(note.get("qty_per_shipping_box")),
                "cases_per_pallet": None,
                "attributes": {
                    "migration": "legacy_django_gwms",
                    "legacy_goods_id": goods.get("id"),
                    "legacy_goods_code": goods.get("goods_code"),
                    "customer_sku": goods.get("customer_sku"),
                    "supplier": goods.get("goods_supplier"),
                    "source_evidence_id": goods.get("source_evidence_id"),
                    "source_note": note,
                    "source_measurement_unit": goods.get("measurement_unit") or "in/lb",
                    "source_dimensions_in": [length_in, width_in, height_in],
                    "source_weight_lb": weight_lb,
                    "legacy_bar_code": goods.get("bar_code"),
                },
                "created_at": dt_or_now(goods.get("create_time")),
                "updated_at": dt_or_now(goods.get("update_time")),
            }
        )

    zone_names = sorted({str(row.get("staging_zone") or "STAGING") for row in bin_rows})
    zones = [
        {
            "id": stable_id("zone", f"{warehouse_id}:{zone_name}"),
            "name": zone_name,
            "code": zone_name,
            "is_agv_zone": False,
            "sequence": index,
            "zone_type": "staging",
        }
        for index, zone_name in enumerate(zone_names, start=1)
    ]
    zone_ids = {zone["code"]: zone["id"] for zone in zones}

    locations = []
    for row in bin_rows:
        zone_name = str(row.get("staging_zone") or "STAGING")
        slot = integer(row.get("staging_slot")) or 0
        locations.append(
            {
                "id": stable_id("location", row.get("id", row.get("bin_name"))),
                "zone_code": zone_name,
                "barcode": str(row.get("bin_name") or row.get("bar_code") or "").strip(),
                "aisle": zone_name[:10],
                "rack": "STAGE",
                "level": "0",
                "position": str(slot),
                "is_agv_accessible": False,
                "location_type": "staging",
                "current_status": "available" if row.get("empty_label", True) else "occupied",
                "pick_sequence": slot,
                "dimensions": {"legacy_bin_size": row.get("bin_size"), "capacity": row.get("slot_capacity")},
                "layout_metadata": {
                    "legacy_bin_id": row.get("id"),
                    "legacy_location_role": row.get("location_role"),
                    "staging_flow": row.get("staging_flow"),
                    "legacy_bar_code": row.get("bar_code"),
                    "source": "legacy production bin master",
                },
            }
        )

    inbound_orders = []
    for asn in asn_rows:
        order_id = stable_id("inbound_order", asn.get("id", asn.get("asn_code")))
        inbound_orders.append(
            {
                "id": order_id,
                "order_number": str(asn.get("asn_code") or f"LEGACY-ASN-{asn.get('id')}"),
                "reference_number": asn.get("container_tracking") or None,
                "status": "expected" if asn.get("asn_status") in (1, "1") else "draft",
                "expected_date": parse_datetime(asn.get("expected_arrival_at")),
                "received_date": parse_datetime(asn.get("actual_arrival_at")),
                "supplier_name": asn.get("supplier") or None,
                "notes": "Migrated from legacy GreaterWMS. No inbound line was present in the production ASN.",
                "extra_data": {
                    "migration": "legacy_django_gwms",
                    "legacy_asn_id": asn.get("id"),
                    "legacy_asn_code": asn.get("asn_code"),
                    "legacy_status": asn.get("asn_status"),
                    "container_tracking": asn.get("container_tracking"),
                    "package_qty": asn.get("package_qty"),
                    "pack_list_status": asn.get("pack_list_status"),
                    "source_evidence_ids": [1, 5],
                    "source_export": export.get("captured_at"),
                },
                "created_at": dt_or_now(asn.get("create_time")),
                "updated_at": dt_or_now(asn.get("update_time")),
                "client_code": extract_code("Delta Electronics (USA) Inc. (56315)", "56315"),
            }
        )

    source_manifest = []
    for source in source_rows:
        metadata = source.get("metadata") or {}
        source_manifest.append(
            {
                "legacy_id": source.get("id"),
                "operation": source.get("operation"),
                "status": source.get("status"),
                "mailbox_account": source.get("mailbox_account"),
                "message_id": source.get("message_id"),
                "content_hash": source.get("content_hash"),
                "subject": metadata.get("subject"),
                "sender": metadata.get("sender") or metadata.get("sender_email"),
            }
        )

    return {
        "schema": 1,
        "source": export.get("source"),
        "captured_at": export.get("captured_at"),
        "tenant": {
            "id": tenant_id,
            "name": TENANT_NAME,
            "code": TENANT_CODE,
            "contact_email": "wuqingxin1978@icloud.com",
            "address": {
                "street": source_warehouse.get("warehouse_address"),
                "city": source_warehouse.get("warehouse_city"),
                "country": "US",
            },
            "source_openid": source_warehouse.get("openid"),
            "source_manifest": source_manifest,
        },
        "warehouse": {
            "id": warehouse_id,
            "name": source_warehouse.get("warehouse_name") or TENANT_NAME,
            "code": "PEAK-LEWISVILLE",
            "address": {
                "street": source_warehouse.get("warehouse_address"),
                "city": source_warehouse.get("warehouse_city"),
                "country": "US",
            },
            "timezone": "America/Chicago",
        },
        "clients": clients,
        "zones": zones,
        "locations": locations,
        "skus": skus,
        "inbound_orders": inbound_orders,
        "source_counts": {
            "customers": len(customer_rows),
            "suppliers": len(supplier_rows),
            "goods": len(goods_rows),
            "bins": len(bin_rows),
            "asn": len(asn_rows),
            "source_evidence": len(source_rows),
            "stock": len(rows(resources, "stock")),
        },
        "target_counts": {
            "clients": len(clients),
            "zones": len(zones),
            "locations": len(locations),
            "skus": len(skus),
            "inbound_orders": len(inbound_orders),
            "inventory": 0,
        },
    }


def build_sql(plan: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    tenant = plan["tenant"]
    warehouse = plan["warehouse"]
    tenant_settings = {
        "migration": {
            "source": "legacy_django_gwms",
            "source_openid": tenant["source_openid"],
            "captured_at": plan["captured_at"],
            "source_counts": plan["source_counts"],
            "source_evidence_manifest": tenant["source_manifest"],
            "raw_export_backup": "greaterwms-production-export-20260825.json",
        }
    }
    statements = [
        "SET app.is_platform_admin = 'true';",
        "BEGIN;",
        "SET LOCAL statement_timeout = '120s';",
        "-- Insert-only migration. Any conflicting business key aborts the transaction.",
        "INSERT INTO tenants (id, name, code, subdomain, contact_email, contact_phone, address, plan_tier, is_active, settings, created_at, updated_at, approval_status, approved_at) VALUES ("
        + ", ".join(
            [
                sql_literal(tenant["id"]),
                sql_literal(tenant["name"]),
                sql_literal(tenant["code"]),
                sql_literal("peaksmart"),
                sql_literal(tenant["contact_email"]),
                "NULL",
                json_sql(tenant["address"]),
                sql_literal("starter"),
                "TRUE",
                json_sql(tenant_settings),
                sql_literal(now),
                sql_literal(now),
                sql_literal("approved"),
                sql_literal(now),
            ]
        )
        + ");",
    ]

    for client in plan["clients"]:
        statements.append(
            "INSERT INTO clients (id, tenant_id, name, code, contact_email, contact_phone, address, notes, billing_enabled, portal_access, is_active, settings, created_at, updated_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(client["id"]),
                    sql_literal(tenant["id"]),
                    sql_literal(client["name"]),
                    sql_literal(client["code"]),
                    sql_literal(client["contact_email"]),
                    sql_literal(client["contact_phone"]),
                    json_sql(client["address"]) if client["address"] else "NULL",
                    sql_literal(f"Source: {client['source']}"),
                    "TRUE",
                    "TRUE",
                    "TRUE",
                    json_sql({"migration": "legacy_django_gwms"}),
                    sql_literal(now),
                    sql_literal(now),
                ]
            )
            + ");"
        )

    statements.append(
        "INSERT INTO warehouses (id, tenant_id, name, code, address, timezone, is_active, created_at, updated_at) VALUES ("
        + ", ".join(
            [
                sql_literal(warehouse["id"]),
                sql_literal(tenant["id"]),
                sql_literal(warehouse["name"]),
                sql_literal(warehouse["code"]),
                json_sql(warehouse["address"]),
                sql_literal(warehouse["timezone"]),
                "TRUE",
                sql_literal(now),
                sql_literal(now),
            ]
        )
        + ");"
    )

    for zone in plan["zones"]:
        statements.append(
            "INSERT INTO zones (id, tenant_id, warehouse_id, name, code, is_agv_zone, sequence, created_at, updated_at, zone_type, dimensions, layout_metadata, drawing_source) VALUES ("
            + ", ".join(
                [
                    sql_literal(zone["id"]),
                    sql_literal(tenant["id"]),
                    sql_literal(warehouse["id"]),
                    sql_literal(zone["name"]),
                    sql_literal(zone["code"]),
                    "FALSE",
                    str(zone["sequence"]),
                    sql_literal(now),
                    sql_literal(now),
                    sql_literal(zone["zone_type"]),
                    "NULL",
                    json_sql({"migration": "legacy_django_gwms"}),
                    "NULL",
                ]
            )
            + ");"
        )

    zone_ids = {zone["code"]: zone["id"] for zone in plan["zones"]}
    for location in plan["locations"]:
        statements.append(
            "INSERT INTO locations (id, tenant_id, warehouse_id, zone_id, barcode, aisle, rack, level, position, coordinate_x, coordinate_y, coordinate_z, is_agv_accessible, location_type, current_status, max_weight_kg, max_volume_m3, pick_sequence, created_at, updated_at, dimensions, layout_metadata, drawing_source, wcs_point_metadata) VALUES ("
            + ", ".join(
                [
                    sql_literal(location["id"]),
                    sql_literal(tenant["id"]),
                    sql_literal(warehouse["id"]),
                    sql_literal(zone_ids[location["zone_code"]]),
                    sql_literal(location["barcode"]),
                    sql_literal(location["aisle"]),
                    sql_literal(location["rack"]),
                    sql_literal(location["level"]),
                    sql_literal(location["position"]),
                    "NULL",
                    "NULL",
                    "NULL",
                    "FALSE",
                    sql_literal(location["location_type"]),
                    sql_literal(location["current_status"]),
                    "NULL",
                    "NULL",
                    str(location["pick_sequence"]),
                    sql_literal(now),
                    sql_literal(now),
                    json_sql(location["dimensions"]),
                    json_sql(location["layout_metadata"]),
                    "NULL",
                    "NULL",
                ]
            )
            + ");"
        )

    for sku in plan["skus"]:
        statements.append(
            "INSERT INTO skus (id, tenant_id, client_id, sku_code, barcode, name, description, weight_kg, length_cm, width_cm, height_cm, requires_lot, requires_expiry, is_hazmat, units_per_case, cases_per_pallet, attributes, created_at, updated_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(sku["id"]),
                    sql_literal(tenant["id"]),
                    sql_literal(next(client["id"] for client in plan["clients"] if client["code"] == sku["client_code"])),
                    sql_literal(sku["sku_code"]),
                    sql_literal(sku["barcode"]),
                    sql_literal(sku["name"]),
                    sql_literal(sku["description"]),
                    str(sku["weight_kg"]),
                    str(sku["length_cm"]),
                    str(sku["width_cm"]),
                    str(sku["height_cm"]),
                    "TRUE" if sku["requires_lot"] else "FALSE",
                    "TRUE" if sku["requires_expiry"] else "FALSE",
                    "TRUE" if sku["is_hazmat"] else "FALSE",
                    str(sku["units_per_case"]) if sku["units_per_case"] is not None else "NULL",
                    "NULL",
                    json_sql(sku["attributes"]),
                    sql_literal(sku["created_at"]),
                    sql_literal(sku["updated_at"]),
                ]
            )
            + ");"
        )

    for order in plan["inbound_orders"]:
        delta_client = next(client for client in plan["clients"] if client["code"] == order["client_code"])
        statements.append(
            "INSERT INTO inbound_orders (id, tenant_id, client_id, warehouse_id, order_number, reference_number, status, expected_date, received_date, supplier_name, notes, extra_data, created_at, updated_at) VALUES ("
            + ", ".join(
                [
                    sql_literal(order["id"]),
                    sql_literal(tenant["id"]),
                    sql_literal(delta_client["id"]),
                    sql_literal(warehouse["id"]),
                    sql_literal(order["order_number"]),
                    sql_literal(order["reference_number"]),
                    sql_literal(order["status"]),
                    sql_literal(order["expected_date"]),
                    sql_literal(order["received_date"]),
                    sql_literal(order["supplier_name"]),
                    sql_literal(order["notes"]),
                    json_sql(order["extra_data"]),
                    sql_literal(order["created_at"]),
                    sql_literal(order["updated_at"]),
                ]
            )
            + ");"
        )

    statements.extend(
        [
            "COMMIT;",
            "SELECT 'migration_complete' AS marker, (SELECT COUNT(*) FROM tenants WHERE id = "
            + sql_literal(tenant["id"])
            + ") AS tenants, (SELECT COUNT(*) FROM warehouses WHERE tenant_id = "
            + sql_literal(tenant["id"])
            + ") AS warehouses, (SELECT COUNT(*) FROM clients WHERE tenant_id = "
            + sql_literal(tenant["id"])
            + ") AS clients, (SELECT COUNT(*) FROM skus WHERE tenant_id = "
            + sql_literal(tenant["id"])
            + ") AS skus, (SELECT COUNT(*) FROM locations WHERE tenant_id = "
            + sql_literal(tenant["id"])
            + ") AS locations, (SELECT COUNT(*) FROM inbound_orders WHERE tenant_id = "
            + sql_literal(tenant["id"])
            + ") AS inbound_orders;",
        ]
    )
    return "\n".join(statements) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sql", type=Path, required=True)
    args = parser.parse_args()

    export = json.loads(args.input.read_text(encoding="utf-8"))
    plan = build_plan(export)
    plan["plan_sha256"] = hashlib.sha256(
        json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    args.sql.write_text(build_sql(plan), encoding="utf-8")
    print(json.dumps({"plan": str(args.plan), "sql": str(args.sql), "plan_sha256": plan["plan_sha256"], "source_counts": plan["source_counts"], "target_counts": plan["target_counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
