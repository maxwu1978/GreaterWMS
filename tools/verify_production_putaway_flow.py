#!/usr/bin/env python3
"""Verify the live receiving -> putaway -> AGV-ready flow against production."""

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


def _find_putaway_task(tasks: list[dict[str, Any]], order_id: str) -> dict[str, Any]:
    for task in tasks:
        if task.get("task_type") == "putaway" and task.get("reference_id") == order_id:
            return task
    raise RuntimeError(f"No putaway task found for inbound order {order_id}")


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
    stop_after_task: bool


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
            if not source and not self.config.allow_autoselect:
                raise RuntimeError(
                    "Source location selection is ambiguous. Set WMS_VERIFY_SOURCE_BARCODE or enable WMS_VERIFY_ALLOW_AUTOSELECT=1."
                )
            if not source:
                raise RuntimeError("No staging or dock location available")

        destinations = _pick_storage_locations(locations, source["id"])
        if not destinations:
            raise RuntimeError("No storage destinations available")

        suffix = "".join(random.choices(string.digits, k=8))
        order_number = f"INB-E2E-{suffix}"
        tracking = f"TRK-E2E-{suffix}"
        carton = f"CTN-E2E-{suffix}"
        customer_barcode = f"CUS-E2E-{suffix}"

        inbound = self.request(
            "POST",
            "/receiving/inbound",
            json={
                "warehouse_id": warehouse["id"],
                "client_id": client["id"],
                "order_number": order_number,
                "reference_number": f"REF-{suffix}",
                "lines": [
                    {
                        "sku_id": sku["id"],
                        "quantity": 5,
                        "external_tracking_number": tracking,
                        "external_carton_mark": carton,
                        "external_customer_barcode": customer_barcode,
                    }
                ],
            },
        )
        order_id = inbound["id"]

        self.request("POST", f"/receiving/inbound/{order_id}/start-receiving")

        scanned = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/scan-label",
            json={"label_code": tracking},
        )

        received = self.request(
            "POST",
            f"/receiving/inbound/{order_id}/receive-label",
            json={
                "label_code": tracking,
                "quantity_received": 5,
                "quantity_damaged": 0,
                "staging_location_id": source["id"],
                "package_count": 2,
                "measured_weight_kg": 9.5,
                "receiving_note": "Automated production verification",
            },
        )

        completed = self.request("POST", f"/receiving/inbound/{order_id}/complete")

        tasks = self.request(
            "GET",
            "/tasks/",
            params={
                "status": "pending",
                "task_type": "putaway",
                "warehouse_id": warehouse["id"],
                "limit": 100,
            },
        )
        task = _find_putaway_task(tasks, order_id)

        agv_pending = self.request(
            "GET",
            "/agv/tasks/pending",
            params={"warehouse_id": warehouse["id"], "task_types": "putaway", "limit": 100},
        )
        agv_task = _find_putaway_task(agv_pending, order_id)

        if self.config.stop_after_task:
            return {
                "warehouse": {"id": warehouse["id"], "code": warehouse.get("code")},
                "client": {"id": client["id"], "code": client.get("code")},
                "sku": {"id": sku["id"], "sku_code": sku.get("sku_code")},
                "order": {"id": order_id, "order_number": order_number},
                "tracking": tracking,
                "scan_match": scanned.get("matched_by"),
                "handling_unit_code": received.get("handling_unit_code"),
                "putaway_task": {
                    "id": task["id"],
                    "status": task.get("status"),
                    "source_location_id": task.get("source_location_id"),
                    "source_location_barcode": task.get("source_location_barcode"),
                    "destination_location_id": task.get("destination_location_id"),
                    "execution_mode": task.get("execution_mode"),
                    "agv_eligible": task.get("agv_eligible"),
                    "execution_reason": task.get("execution_reason"),
                },
                "agv_pending": {
                    "task_id": agv_task["task_id"],
                    "handling_unit_id": agv_task.get("handling_unit_id"),
                    "handling_unit_code": agv_task.get("handling_unit_code"),
                    "handling_unit_status": agv_task.get("handling_unit_status"),
                    "execution_mode": agv_task.get("execution_mode"),
                    "source_barcode": agv_task.get("source_barcode")
                    or (agv_task.get("source") or {}).get("barcode"),
                    "destination_barcode": agv_task.get("destination_barcode")
                    or (agv_task.get("destination") or {}).get("barcode"),
                },
                "complete": {
                    "created_tasks": completed.get("created_tasks"),
                    "putaway_units": completed.get("putaway_units"),
                },
                "next_action": "run_wcs_point_mapping_import_then_dispatch_preview",
            }

        suggestions = _items(
            self.request(
                "POST",
                "/fulfillment/putaway/suggest-location",
                json={
                    "warehouse_id": warehouse["id"],
                    "sku_id": sku["id"],
                    "quantity": task["quantity"],
                    "source_location_id": source["id"],
                },
            )
        )

        chosen_destinations = destinations
        allocations = [
            {"location_id": chosen_destinations[0]["id"], "quantity": 3},
            {"location_id": chosen_destinations[min(1, len(chosen_destinations) - 1)]["id"], "quantity": 2},
        ]
        if len(chosen_destinations) == 1:
            allocations = [{"location_id": chosen_destinations[0]["id"], "quantity": 5}]

        confirmed = self.request(
            "POST",
            "/fulfillment/putaway/confirm",
            json={
                "task_id": task["id"],
                "destination_location_id": allocations[0]["location_id"],
                "allocations": allocations,
            },
        )

        return {
            "warehouse": {"id": warehouse["id"], "code": warehouse.get("code")},
            "client": {"id": client["id"], "code": client.get("code")},
            "sku": {"id": sku["id"], "sku_code": sku.get("sku_code")},
            "order_number": order_number,
            "tracking": tracking,
            "scan_match": scanned.get("matched_by"),
            "handling_unit_code": received.get("handling_unit_code"),
            "putaway_task": {
                "id": task["id"],
                "execution_mode": task.get("execution_mode"),
                "agv_eligible": task.get("agv_eligible"),
                "execution_reason": task.get("execution_reason"),
            },
            "agv_pending": {
                "task_id": agv_task["task_id"],
                "handling_unit_id": agv_task.get("handling_unit_id"),
                "handling_unit_code": agv_task.get("handling_unit_code"),
                "handling_unit_status": agv_task.get("handling_unit_status"),
                "execution_mode": agv_task.get("execution_mode"),
                "source_barcode": agv_task.get("source_barcode") or (agv_task.get("source") or {}).get("barcode"),
                "destination_barcode": agv_task.get("destination_barcode") or (agv_task.get("destination") or {}).get("barcode"),
            },
            "suggestion_count": len(suggestions),
            "allocations": confirmed.get("allocations", []),
            "complete": {
                "created_tasks": completed.get("created_tasks"),
                "putaway_units": completed.get("putaway_units"),
            },
        }


def load_config() -> VerifyConfig:
    api_base = os.getenv("WMS_API_BASE", "https://api.maxsmartwms.online/api/v1")
    email = os.getenv("WMS_VERIFY_EMAIL")
    password = os.getenv("WMS_VERIFY_PASSWORD")
    if not email or not password:
        raise SystemExit("WMS_VERIFY_EMAIL and WMS_VERIFY_PASSWORD must be set")
    request_timeout = float(os.getenv("WMS_VERIFY_TIMEOUT", str(DEFAULT_REQUEST_TIMEOUT)))
    request_retries = int(os.getenv("WMS_VERIFY_RETRIES", str(DEFAULT_REQUEST_RETRIES)))
    warehouse_code = os.getenv("WMS_VERIFY_WAREHOUSE_CODE")
    client_code = os.getenv("WMS_VERIFY_CLIENT_CODE")
    sku_code = os.getenv("WMS_VERIFY_SKU_CODE")
    source_barcode = os.getenv("WMS_VERIFY_SOURCE_BARCODE")
    allow_autoselect = os.getenv("WMS_VERIFY_ALLOW_AUTOSELECT", "").strip().lower() in {"1", "true", "yes"}
    stop_after_task = os.getenv("WMS_VERIFY_STOP_AFTER_TASK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return VerifyConfig(
        api_base=api_base,
        email=email,
        password=password,
        request_timeout=request_timeout,
        request_retries=request_retries,
        warehouse_code=warehouse_code,
        client_code=client_code,
        sku_code=sku_code,
        source_barcode=source_barcode,
        allow_autoselect=allow_autoselect,
        stop_after_task=stop_after_task,
    )


def main() -> int:
    verifier = ProductionVerifier(load_config())
    result = verifier.run()
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
