#!/usr/bin/env python3
"""Verify live inbound lifecycle controls against production."""

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

    def create_inbound(self, warehouse_id: str, client_id: str, sku_id: str, order_number: str, tracking: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/receiving/inbound",
            json={
                "warehouse_id": warehouse_id,
                "client_id": client_id,
                "order_number": order_number,
                "reference_number": f"REF-{order_number}",
                "lines": [
                    {
                        "sku_id": sku_id,
                        "quantity": 1,
                        "external_tracking_number": tracking,
                    }
                ],
            },
        )

    def list_inbound(self, *, include_archived: bool = False, limit: int = 20) -> list[dict[str, Any]]:
        return _items(
            self.request(
                "GET",
                "/orders/inbound",
                params={
                    "include_archived": str(include_archived).lower(),
                    "limit": limit,
                },
            )
        )

    def get_inbound_detail(self, order_id: str) -> dict[str, Any]:
        return self.request("GET", f"/order-details/inbound/{order_id}")

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

        suffix = "".join(random.choices(string.digits, k=8))

        delete_order = self.create_inbound(
            warehouse["id"],
            client["id"],
            sku["id"],
            f"INB-DEL-{suffix}",
            f"TRK-DEL-{suffix}",
        )
        self.request("DELETE", f"/orders/inbound/{delete_order['id']}")

        archive_order = self.create_inbound(
            warehouse["id"],
            client["id"],
            sku["id"],
            f"INB-ARC-{suffix}",
            f"TRK-ARC-{suffix}",
        )
        archived = self.request(
            "POST",
            f"/orders/inbound/{archive_order['id']}/archive",
            json={"archived": True},
        )
        archived_detail = self.get_inbound_detail(archive_order["id"])
        default_after_archive = self.list_inbound(include_archived=False, limit=50)
        archived_after_archive = self.list_inbound(include_archived=True, limit=50)
        restored = self.request(
            "POST",
            f"/orders/inbound/{archive_order['id']}/archive",
            json={"archived": False},
        )
        restored_detail = self.get_inbound_detail(archive_order["id"])

        void_order = self.create_inbound(
            warehouse["id"],
            client["id"],
            sku["id"],
            f"INB-VOID-{suffix}",
            f"TRK-VOID-{suffix}",
        )
        self.request("POST", f"/receiving/inbound/{void_order['id']}/start-receiving")
        self.request(
            "POST",
            f"/receiving/inbound/{void_order['id']}/scan-label",
            json={"label_code": f"TRK-VOID-{suffix}"},
        )
        voided = self.request("POST", f"/orders/inbound/{void_order['id']}/void")
        voided_detail = self.get_inbound_detail(void_order["id"])

        default_orders = self.list_inbound(include_archived=False, limit=50)

        return {
            "warehouse_code": warehouse.get("code"),
            "client_code": client.get("code"),
            "sku_code": sku.get("sku_code"),
            "delete_order_number": delete_order["order_number"],
            "archive_order_number": archive_order["order_number"],
            "archive_hidden_by_default": all(order["id"] != archive_order["id"] for order in default_after_archive),
            "archive_visible_with_toggle": any(
                order["id"] == archive_order["id"] and order.get("archived") is True for order in archived_after_archive
            ),
            "restore_visible_by_default": any(
                order["id"] == archive_order["id"] and order.get("archived") is False for order in default_orders
            ),
            "archive_detail_archived": archived_detail.get("archived"),
            "restore_detail_archived": restored_detail.get("archived"),
            "void_order_number": void_order["order_number"],
            "void_status": voided["status"],
            "void_can_delete": voided["can_delete"],
            "void_can_void": voided["can_void"],
            "void_can_archive": voided["can_archive"],
            "void_detail_voided": voided_detail.get("voided"),
            "void_detail_observed_codes": voided_detail.get("total_observed_codes"),
            "void_detail_internal_labels": voided_detail.get("total_internal_labels"),
            "archived_status": archived["archived"],
            "restored_status": restored["archived"],
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
        allow_autoselect=os.environ.get("WMS_VERIFY_ALLOW_AUTOSELECT") == "1",
    )


def main() -> int:
    verifier = ProductionVerifier(load_config())
    result = verifier.run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
