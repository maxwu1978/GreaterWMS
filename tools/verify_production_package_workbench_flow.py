#!/usr/bin/env python3
"""Verify the live package-centric receiving workbench flow against production."""

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

        suffix = "".join(random.choices(string.digits, k=8))
        order_number = f"INB-PKGWB-{suffix}"
        tracking_primary = f"TRK-PKGWB-{suffix}-1"
        carton_primary = f"CTN-PKGWB-{suffix}-1"
        observed_secondary = f"TRK-PKGWB-{suffix}-2"
        delete_tracking = f"TRK-PKGWB-{suffix}-D"

        inbound = self.request(
            "POST",
            "/receiving/inbound",
            json={
                "warehouse_id": warehouse["id"],
                "client_id": client["id"],
                "order_number": order_number,
                "reference_number": f"REF-PKGWB-{suffix}",
                "lines": [{"sku_id": sku["id"], "quantity": 9}],
            },
        )
        order_id = inbound["id"]
        self.request("POST", f"/receiving/inbound/{order_id}/start-receiving")

        detail = self.request("GET", f"/order-details/inbound/{order_id}")
        line = detail["lines"][0]
        line_id = line["line_id"]

        primary_package = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages",
            json={
                "line_id": line_id,
                "expected_qty": 4,
                "package_type": "carton",
                "external_tracking_number": tracking_primary,
                "external_carton_mark": carton_primary,
            },
        )

        no_code_package = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages",
            json={"line_id": line_id, "expected_qty": 5, "package_type": "crate"},
        )

        delete_candidate = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages",
            json={
                "line_id": line_id,
                "expected_qty": 1,
                "package_type": "carton",
                "external_tracking_number": delete_tracking,
            },
        )

        updated_delete_candidate = self.request(
            "PATCH",
            f"/receiving/inbound/{order_id}/packages/{delete_candidate['id']}",
            json={
                "expected_qty": 2,
                "package_type": "pallet",
                "external_tracking_number": delete_tracking,
            },
        )
        self.request("DELETE", f"/receiving/inbound/{order_id}/packages/{delete_candidate['id']}")

        opened_no_code = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages/{no_code_package['id']}/open",
        )
        observed_code = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/captured-codes",
            json={
                "package_id": no_code_package["id"],
                "code_value": observed_secondary,
                "code_type": "tracking_number",
                "source": "manual",
                "is_primary": True,
            },
        )
        observed_codes = self.request(
            "GET",
            f"/receiving/inbound/{order_id}/captured-codes",
            params={"package_id": no_code_package["id"]},
        )

        scan_primary = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/scan-label",
            json={"label_code": tracking_primary, "source": "scan"},
        )
        scan_secondary = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/scan-label",
            json={"label_code": observed_secondary, "source": "manual"},
        )

        receipt_primary = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages/{primary_package['id']}/receive",
            json={
                "quantity_received": 4,
                "quantity_damaged": 0,
                "staging_location_id": source["id"],
                "package_count": 1,
                "pallet_count": 1,
                "measured_weight_kg": 6.1,
                "receiving_note": "Primary package verification",
            },
        )
        receipt_secondary = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages/{no_code_package['id']}/receive",
            json={
                "quantity_received": 5,
                "quantity_damaged": 0,
                "staging_location_id": source["id"],
                "package_count": 2,
                "pallet_count": 1,
                "measured_weight_kg": 7.2,
                "receiving_note": "Manual package verification",
            },
        )

        completed = self.request("POST", f"/receiving/inbound/{order_id}/complete")
        final_detail = self.request("GET", f"/order-details/inbound/{order_id}")
        packages = final_detail["lines"][0]["packages"]

        return {
            "warehouse_code": warehouse.get("code"),
            "client_code": client.get("code"),
            "sku_code": sku.get("sku_code"),
            "source_barcode": source.get("barcode"),
            "order_number": order_number,
            "line_id": line_id,
            "created_package_ids": [primary_package["id"], no_code_package["id"]],
            "deleted_package_id": delete_candidate["id"],
            "updated_delete_candidate": updated_delete_candidate,
            "opened_no_code_package": {
                "package_id": opened_no_code.get("package_id"),
                "package_number": opened_no_code.get("package_number"),
                "opened_directly": opened_no_code.get("opened_directly"),
                "label_code": opened_no_code.get("label_code"),
            },
            "observed_code": {
                "id": observed_code.get("id"),
                "code_value": observed_code.get("code_value"),
                "package_id": observed_code.get("package_id"),
            },
            "observed_code_count": len(observed_codes),
            "scan_matches": [
                {
                    "matched_by": scan_primary.get("matched_by"),
                    "package_id": scan_primary.get("package_id"),
                    "package_number": scan_primary.get("package_number"),
                },
                {
                    "matched_by": scan_secondary.get("matched_by"),
                    "package_id": scan_secondary.get("package_id"),
                    "package_number": scan_secondary.get("package_number"),
                },
            ],
            "receipts": [receipt_primary, receipt_secondary],
            "complete_summary": completed,
            "final_packages": [
                {
                    "id": package.get("id"),
                    "package_number": package.get("package_number"),
                    "status": package.get("status"),
                    "expected_qty": package.get("expected_qty"),
                    "observed_codes": len(package.get("observed_codes", [])),
                    "receiving_labels": [label.get("label_code") for label in package.get("receiving_labels", [])],
                    "handling_units": [unit.get("unit_code") for unit in package.get("handling_units", [])],
                    "downstream_tasks": len(package.get("downstream_tasks", [])),
                }
                for package in packages
            ],
        }


def main() -> None:
    email = os.environ.get("WMS_VERIFY_EMAIL")
    password = os.environ.get("WMS_VERIFY_PASSWORD")
    if not email or not password:
        raise RuntimeError("WMS_VERIFY_EMAIL and WMS_VERIFY_PASSWORD are required")

    verifier = ProductionVerifier(
        VerifyConfig(
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
    )
    print(json.dumps(verifier.run(), indent=2))


if __name__ == "__main__":
    main()
