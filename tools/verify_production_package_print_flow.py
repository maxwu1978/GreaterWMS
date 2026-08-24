#!/usr/bin/env python3
"""Verify package-centric internal-label printing against production."""

from __future__ import annotations

import json
import os
import random
import string
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_REQUEST_RETRIES = 2


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    return []


def _match_by_field(
    items: list[dict[str, Any]],
    field: str,
    expected: str | None,
    label: str,
    allow_autoselect: bool,
) -> dict[str, Any]:
    if expected:
        for item in items:
            if item.get(field) == expected:
                return item
        raise RuntimeError(f"{label} with {field}={expected!r} was not found")
    if not allow_autoselect:
        raise RuntimeError(
            f"{label} selection is ambiguous. Set WMS_VERIFY_{label.upper().replace(' ', '_')}_CODE or enable WMS_VERIFY_ALLOW_AUTOSELECT=1."
        )
    if not items:
        raise RuntimeError(f"No {label.lower()}s available")
    return items[0]


@dataclass
class VerifyConfig:
    api_base: str
    email: str
    password: str
    request_timeout: float
    request_retries: int
    warehouse_code: str | None
    client_code: str | None
    sku_code: str | None
    source_barcode: str | None
    allow_autoselect: bool


class ProductionVerifier:
    def __init__(self, config: VerifyConfig) -> None:
        self.config = config
        self.session = requests.Session()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        print(f"[verify] {method} {path}", file=sys.stderr, flush=True)
        last_exc: Exception | None = None
        for attempt in range(self.config.request_retries + 1):
            try:
                response = self.session.request(
                    method,
                    f"{self.config.api_base}{path}",
                    timeout=self.config.request_timeout,
                    **kwargs,
                )
                break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= self.config.request_retries:
                    raise RuntimeError(f"Request failed for {method} {path}: {exc}") from exc
                print(
                    f"[verify] retrying {method} {path} after error: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"Request failed for {method} {path}: {last_exc}")
        response.raise_for_status()
        if not response.text:
            return {}
        return response.json()

    def login(self) -> None:
        payload = self.request(
            "POST",
            "/auth/login",
            json={"email": self.config.email, "password": self.config.password},
        )
        self.session.headers.update({"Authorization": f"Bearer {payload['access_token']}"})

    def run(self) -> dict[str, Any]:
        self.login()

        warehouses = _items(self.request("GET", "/warehouses/"))
        warehouse = _match_by_field(
            warehouses, "code", self.config.warehouse_code, "warehouse", self.config.allow_autoselect
        )
        clients = _items(self.request("GET", "/clients"))
        client = _match_by_field(
            clients, "code", self.config.client_code, "client", self.config.allow_autoselect
        )
        skus = _items(self.request("GET", "/skus", params={"offset": 0, "limit": 200}))
        sku = _match_by_field(skus, "sku_code", self.config.sku_code, "SKU", self.config.allow_autoselect)

        locations = _items(self.request("GET", f"/warehouses/{warehouse['id']}/locations"))
        if self.config.source_barcode:
            source = next((location for location in locations if location.get("barcode") == self.config.source_barcode), None)
            if not source:
                raise RuntimeError(f"Source location with barcode={self.config.source_barcode!r} was not found")
        else:
            source = next(
                (
                    location
                    for location in locations
                    if location.get("barcode", "").startswith("DOCK-")
                    or location.get("location_type") == "staging"
                ),
                None,
            )
            if not source:
                raise RuntimeError("No staging or dock location available")

        template_before = self.request("GET", "/tenants/current/receiving-label-template")
        template_payload = {
            "fields": [
                "order_number",
                "package_number",
                "package_type",
                "tracking_number",
                "package_count",
                "pallet_count",
                "weight",
                "receiving_note",
            ],
            "show_field_labels": True,
        }
        self.request("PATCH", "/tenants/current/receiving-label-template", json=template_payload)

        suffix = "".join(random.choices(string.digits, k=8))
        order_number = f"INB-PKGPRT-{suffix}"
        tracking_codes = [f"TRK-PKGPRT-{suffix}-1", f"TRK-PKGPRT-{suffix}-2"]
        package_types = ["carton", "crate"]

        try:
            inbound = self.request(
                "POST",
                "/receiving/inbound",
                json={
                    "warehouse_id": warehouse["id"],
                    "client_id": client["id"],
                    "order_number": order_number,
                    "reference_number": f"REF-PKGPRT-{suffix}",
                    "lines": [{"sku_id": sku["id"], "quantity": 7}],
                },
            )
            order_id = inbound["id"]

            self.request("POST", f"/receiving/inbound/{order_id}/start-receiving")
            detail = self.request("GET", f"/order-details/inbound/{order_id}")
            line_id = detail["lines"][0]["line_id"]

            packages = []
            receipts = []
            for idx, package_type in enumerate(package_types, start=1):
                package = self.request(
                    "POST",
                    f"/receiving/inbound/{order_id}/packages",
                    json={
                        "line_id": line_id,
                        "expected_qty": 3 if idx == 1 else 4,
                        "package_type": package_type,
                        "external_tracking_number": tracking_codes[idx - 1],
                    },
                )
                packages.append(package)
                self.request(
                    "POST",
                    f"/receiving/inbound/{order_id}/scan-label",
                    json={"label_code": tracking_codes[idx - 1], "source": "scan"},
                )
                receipts.append(
                    self.request(
                        "POST",
                        f"/receiving/inbound/{order_id}/packages/{package['id']}/receive",
                        json={
                            "quantity_received": 3 if idx == 1 else 4,
                            "quantity_damaged": 0,
                            "staging_location_id": source["id"],
                            "package_count": idx,
                            "pallet_count": 1,
                            "measured_weight_kg": 5.5 + idx,
                            "receiving_note": f"Package print verification {idx}",
                        },
                    )
                )

            labels_before_print = self.request("GET", f"/receiving/inbound/{order_id}/labels")
            print_result = self.request(
                "POST",
                f"/receiving/inbound/{order_id}/labels/mark-printed",
                json={"label_codes": [label["label_code"] for label in labels_before_print]},
            )
            labels_after_print = self.request("GET", f"/receiving/inbound/{order_id}/labels")

            return {
                "warehouse_code": warehouse.get("code"),
                "client_code": client.get("code"),
                "sku_code": sku.get("sku_code"),
                "order_number": order_number,
                "template_fields": template_payload["fields"],
                "package_numbers": [package["package_number"] for package in packages],
                "package_types": [label.get("package_type") for label in labels_before_print],
                "internal_labels": [label["label_code"] for label in labels_before_print],
                "packaging": [
                    {
                        "package_number": label.get("package_number"),
                        "package_count": label.get("package_count"),
                        "pallet_count": label.get("pallet_count"),
                        "measured_weight_kg": label.get("measured_weight_kg"),
                        "receiving_note": label.get("receiving_note"),
                    }
                    for label in labels_before_print
                ],
                "print_updated": print_result.get("updated"),
                "print_counts_after": [label.get("print_count") for label in labels_after_print],
                "receipts": receipts,
            }
        finally:
            self.request(
                "PATCH",
                "/tenants/current/receiving-label-template",
                json={
                    "fields": template_before.get("fields", []),
                    "show_field_labels": template_before.get("show_field_labels", True),
                },
            )


def load_config() -> VerifyConfig:
    email = os.environ.get("WMS_VERIFY_EMAIL")
    password = os.environ.get("WMS_VERIFY_PASSWORD")
    if not email or not password:
        raise RuntimeError("WMS_VERIFY_EMAIL and WMS_VERIFY_PASSWORD are required")

    return VerifyConfig(
        api_base=os.environ.get("WMS_VERIFY_API_BASE", "https://api.maxsmartwms.online/api/v1"),
        email=email,
        password=password,
        request_timeout=float(os.environ.get("WMS_VERIFY_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)),
        request_retries=int(os.environ.get("WMS_VERIFY_RETRIES", DEFAULT_REQUEST_RETRIES)),
        warehouse_code=os.environ.get("WMS_VERIFY_WAREHOUSE_CODE"),
        client_code=os.environ.get("WMS_VERIFY_CLIENT_CODE"),
        sku_code=os.environ.get("WMS_VERIFY_SKU_CODE"),
        source_barcode=os.environ.get("WMS_VERIFY_SOURCE_BARCODE"),
        allow_autoselect=os.environ.get("WMS_VERIFY_ALLOW_AUTOSELECT") == "1",
    )


def main() -> int:
    verifier = ProductionVerifier(load_config())
    result = verifier.run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
