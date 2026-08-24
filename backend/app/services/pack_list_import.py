"""Parsing and normalization for customer pack-list imports."""

import csv
import hashlib
import io
import json
from typing import Any

from fastapi import HTTPException

from app.services.csv_import import normalize_header, parse_mapping

PACK_LIST_REQUIRED_FIELDS = [
    "order_number",
    "client_code",
    "warehouse_code",
    "package_code",
    "sku_code",
    "quantity",
]

PACK_LIST_OPTIONAL_FIELDS = [
    "container_tracking",
    "customer_sku",
    "item_name",
    "serial_number",
    "line_number",
]

PACK_LIST_ALIASES = {
    "order_number": [
        "order_number",
        "inbound_order",
        "inboundorder",
        "inbound_order_number",
        "asn",
        "reference_number",
    ],
    "client_code": [
        "client_code",
        "client",
        "customer_code",
        "customer",
        "owner",
    ],
    "warehouse_code": [
        "warehouse_code",
        "warehouse",
        "site_code",
        "site",
        "facility",
        "facility_code",
    ],
    "container_tracking": [
        "container_tracking",
        "container_tracking_number",
        "container",
        "tracking",
        "tracking_number",
        "container_trackin",
    ],
    "package_code": [
        "package_code",
        "package_id",
        "package_type",
        "package_number",
        "package_no",
        "carton_number",
        "carton_no",
    ],
    "sku_code": [
        "sku_code",
        "sku",
        "item_code",
        "item_no",
        "item_number",
        "product_code",
        "part_number",
    ],
    "quantity": [
        "quantity",
        "qty",
        "item_qty",
        "total_qty",
        "total",
        "units",
        "pieces",
    ],
    "customer_sku": [
        "customer_sku",
        "s_sku",
        "customer_item",
        "customer_part_number",
    ],
    "item_name": ["item_name", "product_name", "description", "name"],
    "serial_number": ["serial_number", "serial", "sn", "s_n"],
    "line_number": ["line_number", "line_no", "line"],
}

_ALL_FIELDS = PACK_LIST_REQUIRED_FIELDS + PACK_LIST_OPTIONAL_FIELDS


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _canonical_field(name: str) -> str | None:
    normalized = normalize_header(name)
    for target, aliases in PACK_LIST_ALIASES.items():
        if normalized == normalize_header(target) or normalized in {
            normalize_header(alias) for alias in aliases
        }:
            return target
    return None


def _canonicalize_json_row(row: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in row.items():
        target = _canonical_field(str(key))
        if target:
            result[target] = _clean(value)
    return result


def _parse_json_source(source_text: str) -> tuple[dict[str, str], list[dict[str, str]], dict]:
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Pack List JSON must be valid JSON") from exc

    if isinstance(payload, list):
        metadata: dict[str, Any] = {}
        raw_rows = payload
    elif isinstance(payload, dict):
        metadata = {
            field: _clean(value)
            for key, value in payload.items()
            if (field := _canonical_field(str(key))) and not isinstance(value, (dict, list))
        }
        raw_rows = payload.get("rows") or payload.get("lines") or payload.get("items") or []
    else:
        raise HTTPException(status_code=400, detail="Pack List JSON must be an object or array")

    if not isinstance(raw_rows, list) or not raw_rows:
        raise HTTPException(status_code=400, detail="Pack List JSON must contain a non-empty rows array")
    rows = [
        _canonicalize_json_row(row)
        for row in raw_rows
        if isinstance(row, dict)
    ]
    if len(rows) != len(raw_rows):
        raise HTTPException(status_code=400, detail="Every Pack List JSON row must be an object")
    return metadata, rows, {}


def _parse_csv_source(
    file_name: str,
    source_text: str,
    mapping_json: dict[str, str] | None,
) -> tuple[dict[str, str], list[dict[str, str]], dict]:
    if not file_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Pack List imports accept .csv or .json files")
    decoded = source_text.encode("utf-8-sig").decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    headers = list(reader.fieldnames or [])
    if not headers:
        raise HTTPException(status_code=400, detail="Pack List CSV must include a header row")
    mapping = parse_mapping(
        mapping_json,
        headers,
        aliases=PACK_LIST_ALIASES,
        required_fields=[],
        optional_fields=_ALL_FIELDS,
    )
    rows = []
    for source_row in reader:
        rows.append(
            {
                target: _clean(source_row.get(header))
                for target, header in mapping.items()
            }
        )
    if not rows:
        raise HTTPException(status_code=400, detail="Pack List CSV must contain at least one data row")
    return {}, rows, {"mapping_used": mapping, "headers": headers}


def parse_pack_list_source(
    *,
    file_name: str,
    source_text: str,
    mapping: dict[str, str] | None = None,
    overrides: dict[str, str | None] | None = None,
) -> dict:
    """Parse a CSV/JSON source into canonical rows without touching the database."""

    if not source_text.strip():
        raise HTTPException(status_code=400, detail="Pack List source is empty")
    if file_name.lower().endswith(".json"):
        metadata, rows, parser_meta = _parse_json_source(source_text)
    else:
        metadata, rows, parser_meta = _parse_csv_source(file_name, source_text, mapping)

    effective_overrides = {key: _clean(value) for key, value in (overrides or {}).items() if value}
    for row in rows:
        for field, value in metadata.items():
            row.setdefault(field, value)
        for field, value in effective_overrides.items():
            row[field] = value

    return {
        "rows": rows,
        "parser_meta": parser_meta,
        "source_checksum": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "document_defaults": metadata,
    }


def parse_positive_quantity(value: str, row_number: int) -> int | None:
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


__all__ = [
    "PACK_LIST_ALIASES",
    "PACK_LIST_OPTIONAL_FIELDS",
    "PACK_LIST_REQUIRED_FIELDS",
    "parse_pack_list_source",
    "parse_positive_quantity",
]
