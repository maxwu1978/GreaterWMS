#!/usr/bin/env python3
"""Verify the live package-centric receiving -> detail -> putaway flow against production."""

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


def _pick_storage_locations(locations: list[dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    storage = [
        location
        for location in locations
        if location.get("id") != source_id and location.get("location_type") == "storage"
    ]
    return storage[:2]


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
        token = payload["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def run(self) -> dict[str, Any]:
        self.login()

        warehouses = _items(self.request("GET", "/warehouses/"))
        warehouse = _match_by_field(
            warehouses,
            "code",
            self.config.warehouse_code,
            "warehouse",
            self.config.allow_autoselect,
        )

        clients = _items(self.request("GET", "/clients"))
        client = _match_by_field(
            clients,
            "code",
            self.config.client_code,
            "client",
            self.config.allow_autoselect,
        )

        skus = _items(self.request("GET", "/skus", params={"offset": 0, "limit": 200}))
        sku = _match_by_field(
            skus,
            "sku_code",
            self.config.sku_code,
            "SKU",
            self.config.allow_autoselect,
        )

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
        destinations = _pick_storage_locations(locations, source["id"])
        if len(destinations) < 2:
            raise RuntimeError("At least two storage destinations are required for package verification")

        suffix = "".join(random.choices(string.digits, k=8))
        order_number = f"INB-PKGDTL-{suffix}"
        inbound = self.request(
            "POST",
            "/receiving/inbound",
            json={
                "warehouse_id": warehouse["id"],
                "client_id": client["id"],
                "order_number": order_number,
                "reference_number": f"REF-PKGDTL-{suffix}",
                "lines": [{"sku_id": sku["id"], "quantity": 10}],
            },
        )
        order_id = inbound["id"]

        detail = self.request("GET", f"/order-details/inbound/{order_id}")
        line_id = detail["lines"][0]["line_id"]

        tracking_codes = [f"TRK-PKGDTL-{suffix}-1", f"TRK-PKGDTL-{suffix}-2"]
        carton_codes = [f"CTN-PKGDTL-{suffix}-1", f"CTN-PKGDTL-{suffix}-2"]
        expected_qtys = [4, 6]

        self.request("POST", f"/receiving/inbound/{order_id}/start-receiving")
        packages: list[dict[str, Any]] = []
        scans: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        for idx in range(2):
            package = self.request(
                "POST",
                f"/receiving/inbound/{order_id}/packages",
                json={
                    "line_id": line_id,
                    "expected_qty": expected_qtys[idx],
                    "package_type": "carton",
                    "external_tracking_number": tracking_codes[idx],
                    "external_carton_mark": carton_codes[idx],
                },
            )
            packages.append(package)

            scans.append(
                self.request(
                    "POST",
                    f"/receiving/inbound/{order_id}/scan-label",
                    json={"label_code": tracking_codes[idx], "source": "scan"},
                )
            )
            receipts.append(
                self.request(
                    "POST",
                    f"/receiving/inbound/{order_id}/packages/{package['id']}/receive",
                    json={
                        "quantity_received": expected_qtys[idx],
                        "quantity_damaged": 0,
                        "staging_location_id": source["id"],
                        "package_count": idx + 1,
                        "pallet_count": 1,
                        "measured_weight_kg": 4.0 + (idx * 2.1),
                        "receiving_note": f"Package detail verification {idx + 1}",
                    },
                )
            )

        completed = self.request("POST", f"/receiving/inbound/{order_id}/complete")
        pending_detail = self.request("GET", f"/order-details/inbound/{order_id}")
        pending_packages = {pkg["package_number"]: pkg for pkg in pending_detail["lines"][0]["packages"]}

        tasks = _items(
            self.request(
                "GET",
                "/tasks/",
                params={"warehouse_id": warehouse["id"], "task_type": "putaway", "limit": 100},
            )
        )
        order_tasks = [task for task in tasks if task.get("reference_id") == order_id]
        order_tasks.sort(key=lambda task: task.get("handling_unit_code") or "")
        confirmations = []
        for task, destination in zip(order_tasks, destinations):
            confirmations.append(
                self.request(
                    "POST",
                    "/fulfillment/putaway/confirm",
                    json={
                        "task_id": task["id"],
                        "destination_location_id": destination["id"],
                        "allocations": [{"location_id": destination["id"], "quantity": task["quantity"]}],
                    },
                )
            )

        completed_detail = self.request("GET", f"/order-details/inbound/{order_id}")
        completed_packages = {pkg["package_number"]: pkg for pkg in completed_detail["lines"][0]["packages"]}

        return {
            "warehouse_code": warehouse.get("code"),
            "client_code": client.get("code"),
            "sku_code": sku.get("sku_code"),
            "order_number": order_number,
            "package_numbers": [package["package_number"] for package in packages],
            "scan_matches": [scan.get("matched_by") for scan in scans],
            "scan_package_numbers": [scan.get("package_number") for scan in scans],
            "internal_labels": [receipt.get("handling_unit_code") for receipt in receipts],
            "complete": {
                "created_tasks": completed.get("created_tasks"),
                "putaway_units": completed.get("putaway_units"),
            },
            "pending_package_statuses": {
                str(number): pending_packages[number]["status"] for number in sorted(pending_packages)
            },
            "pending_package_task_counts": {
                str(number): len(pending_packages[number]["downstream_tasks"]) for number in sorted(pending_packages)
            },
            "pending_downstream_summary": pending_detail.get("downstream_summary"),
            "putaway_destinations": [destination["barcode"] for destination in destinations[: len(order_tasks)]],
            "completed_downstream_summary": completed_detail.get("downstream_summary"),
            "completed_package_statuses": {
                str(number): completed_packages[number]["status"] for number in sorted(completed_packages)
            },
            "completed_package_unit_statuses": {
                str(number): [unit["status"] for unit in completed_packages[number]["handling_units"]]
                for number in sorted(completed_packages)
            },
            "completed_package_task_statuses": {
                str(number): [task["status"] for task in completed_packages[number]["downstream_tasks"]]
                for number in sorted(completed_packages)
            },
            "confirmations": confirmations,
        }


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
