"""Shared CSV import helpers — header normalization, row loading, and field mapping.

Used by the orders, receiving, agent, and data_import endpoints. The mapping
helpers are parameterized by each caller's field-alias map and required/optional
field lists so behavior stays identical to the original per-endpoint copies.
"""

import csv
import io
import json
import re
from collections.abc import Callable

from fastapi import HTTPException


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def load_csv_rows(
    file_name: str | None,
    content: bytes,
    *,
    encoding: str = "utf-8-sig",
    strict: bool = True,
) -> tuple[list[str], list[dict[str, str]]]:
    """Validate the file name, decode the content, and return (headers, rows).

    With ``strict=True`` (default), a bad encoding or a missing header row raises
    an HTTP 400. With ``strict=False``, decode errors propagate unchanged and an
    empty header row is allowed (legacy data_import behavior).
    """
    if file_name and not file_name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    if strict:
        try:
            decoded = content.decode(encoding)
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    else:
        decoded = content.decode(encoding)

    reader = csv.DictReader(io.StringIO(decoded))
    headers = list(reader.fieldnames or [])
    if strict and not headers:
        raise HTTPException(status_code=400, detail="CSV must include a header row")
    return headers, list(reader)


def suggest_mapping(
    headers: list[str],
    aliases: dict[str, list[str]],
    *,
    normalize: Callable[[str], str] = normalize_header,
) -> dict[str, str]:
    normalized_headers = {normalize(header): header for header in headers}
    mapping: dict[str, str] = {}
    for target_field, field_aliases in aliases.items():
        for alias in field_aliases:
            matched = normalized_headers.get(normalize(alias))
            if matched:
                mapping[target_field] = matched
                break
    return mapping


def parse_mapping(
    mapping_json: str | dict[str, str] | None,
    headers: list[str],
    *,
    aliases: dict[str, list[str]],
    required_fields: list[str],
    optional_fields: list[str],
) -> dict[str, str]:
    allowed_headers = set(headers)
    mapping = suggest_mapping(headers, aliases)
    if mapping_json:
        if isinstance(mapping_json, dict):
            provided_mapping = mapping_json
        else:
            try:
                provided_mapping = json.loads(mapping_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400, detail="Import mapping must be valid JSON"
                ) from exc
        if not isinstance(provided_mapping, dict):
            raise HTTPException(status_code=400, detail="Import mapping must be a JSON object")
        mapping = {
            str(target): str(source)
            for target, source in provided_mapping.items()
            if isinstance(target, str) and isinstance(source, str) and source
        }

    for target_field, header_name in mapping.items():
        if target_field not in required_fields + optional_fields:
            raise HTTPException(status_code=400, detail=f"Unknown import field '{target_field}'")
        if header_name not in allowed_headers:
            raise HTTPException(
                status_code=400,
                detail=f"CSV header '{header_name}' was not found in the uploaded file",
            )

    missing_required = [field for field in required_fields if not mapping.get(field)]
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field mappings: {', '.join(missing_required)}",
        )
    return mapping
