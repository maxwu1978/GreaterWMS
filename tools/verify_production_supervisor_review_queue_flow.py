#!/usr/bin/env python3
"""Verify supervisor-review and recently-changed queue signals against production."""

from __future__ import annotations

import json
import os
import random
import string
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_REQUEST_RETRIES = 2
RECENT_ACTIVITY_WINDOW_HOURS = 12


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

        suffix = "".join(random.choices(string.digits, k=8))
        order_number = f"INB-SUPQ-{suffix}"
        tracking_prebooked = f"TRK-SUPQ-{suffix}-1"
        carton_dock = f"CTN-SUPQ-{suffix}-2"

        inbound = self.request(
            "POST",
            "/receiving/inbound",
            json={
                "warehouse_id": warehouse["id"],
                "client_id": client["id"],
                "order_number": order_number,
                "reference_number": f"REF-SUPQ-{suffix}",
                "lines": [{"line_number": 41, "sku_id": sku["id"], "quantity": 5}],
            },
        )
        order_id = inbound["id"]

        detail_before = self.request("GET", f"/order-details/inbound/{order_id}")
        line_id = detail_before["lines"][0]["line_id"]

        prebooked_package = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages",
            json={
                "line_id": line_id,
                "expected_qty": 3,
                "package_type": "carton",
                "external_tracking_number": tracking_prebooked,
            },
        )

        self.request("POST", f"/receiving/inbound/{order_id}/start-receiving")

        dock_package = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages",
            json={
                "line_id": line_id,
                "expected_qty": 2,
                "package_type": "crate",
                "external_carton_mark": carton_dock,
            },
        )

        receipt = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/packages/{prebooked_package['id']}/receive",
            json={
                "quantity_received": 3,
                "quantity_damaged": 0,
                "staging_location_id": source["id"],
                "package_count": 1,
                "pallet_count": 1,
                "measured_weight_kg": 6.2,
                "receiving_note": "Supervisor review queue verification",
            },
        )

        listed_orders = _items(
            self.request(
                "GET",
                "/orders/inbound",
                params={"include_archived": "false", "limit": 100},
            )
        )
        listed = next(order for order in listed_orders if order.get("id") == order_id)
        detail_after = self.request("GET", f"/order-details/inbound/{order_id}")

        latest_activity_at = listed.get("latest_activity_at")
        if not latest_activity_at:
            raise RuntimeError("orders/inbound did not expose latest_activity_at")
        latest_activity = datetime.fromisoformat(latest_activity_at.replace("Z", "+00:00"))
        if latest_activity < datetime.now(UTC) - timedelta(hours=RECENT_ACTIVITY_WINDOW_HOURS):
            raise RuntimeError("latest_activity_at did not fall inside the recent activity window")

        if not listed.get("supervisor_review_needed"):
            raise RuntimeError("orders/inbound did not flag supervisor_review_needed")
        if not detail_after.get("package_summary", {}).get("supervisor_review_needed"):
            raise RuntimeError("order-details package_summary did not flag supervisor_review_needed")

        return {
            "warehouse_code": warehouse.get("code"),
            "client_code": client.get("code"),
            "sku_code": sku.get("sku_code"),
            "source_barcode": source.get("barcode"),
            "order_number": order_number,
            "prebooked_package_number": prebooked_package.get("package_number"),
            "dock_package_number": dock_package.get("package_number"),
            "receipt_internal_label": receipt.get("label_code"),
            "orders_list_summary": {
                "total_packages": listed.get("total_packages"),
                "packages_open": listed.get("packages_open"),
                "packages_putaway_pending": listed.get("packages_putaway_pending"),
                "packages_prebooked": listed.get("packages_prebooked"),
                "packages_dock_created": listed.get("packages_dock_created"),
                "supervisor_review_needed": listed.get("supervisor_review_needed"),
                "internal_labels_print_pending": listed.get("internal_labels_print_pending"),
                "latest_activity_at": latest_activity_at,
            },
            "detail_package_summary": detail_after.get("package_summary", {}),
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
