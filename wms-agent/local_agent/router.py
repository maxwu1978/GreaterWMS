"""Small deterministic router for the local-agent MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadRoute:
    tool_name: str
    args: dict[str, Any]
    label: str


WRITE_TERMS = [
    "adjust",
    "apply",
    "cancel",
    "confirm",
    "create",
    "delete",
    "hold",
    "import",
    "release",
    "remove",
    "ship",
    "update",
    "void",
    "刪除",
    "删除",
    "修改",
    "新增",
    "確認",
    "确认",
    "凍結",
    "冻结",
]


def looks_like_write(prompt: str) -> bool:
    text = prompt.lower()
    return any(term in text for term in WRITE_TERMS)


def route_prompt(prompt: str) -> tuple[str | None, dict[str, Any]]:
    text = prompt.lower()
    if any(
        word in text
        for word in ["agent setting", "agent config", "agent settings", "agent 配置"]
    ):
        return "settings.agent.get", {}
    if any(
        word in text
        for word in ["receiving code", "receive code", "入库码", "入庫碼", "收货码", "收貨碼"]
    ):
        if "preview" in text or "预览" in text or "預覽" in text:
            return "settings.receiving_codes.preview", {}
        return "settings.receiving_codes.get", {}
    if any(
        word in text
        for word in ["receiving label", "receive label", "label template", "入库标签", "入庫標籤"]
    ):
        if "preview" in text or "预览" in text or "預覽" in text:
            return "settings.receiving_labels.preview", {}
        return "settings.receiving_labels.get", {}
    if any(word in text for word in ["permission", "permissions", "权限", "權限"]):
        return "settings.permissions.explain", {}
    if any(word in text for word in ["user setting", "users", "user list", "用户", "用戶"]):
        return "settings.users.list", {"limit": 20}
    if any(word in text for word in ["client profile", "customer profile", "客户资料", "客戶資料"]):
        if "preview" in text or "预览" in text or "預覽" in text:
            return "settings.client_profile.preview", {"query": prompt, "limit": 8}
        return "settings.client_profile.get", {"query": prompt, "limit": 8}
    if any(word in text for word in ["sku preview", "product preview", "商品预览", "商品預覽"]):
        return "settings.sku.preview", {"query": prompt}
    if any(
        word in text
        for word in ["billing setup", "billing profile", "invoice setting", "发票设置", "發票設定"]
    ):
        return "settings.billing.explain", {}
    if any(word in text for word in ["warehouse location", "locations", "库位", "庫位"]):
        if "preview" in text or "预览" in text or "預覽" in text:
            return "settings.warehouse_location.preview", {"limit": 25}
        return "settings.warehouse_locations.list", {"limit": 25}
    if any(
        word in text
        for word in [
            "blueprint",
            "floor plan",
            "layout plan",
            "仓库图纸",
            "倉庫圖紙",
            "区域规划",
            "區域規劃",
        ]
    ):
        return "warehouse.blueprint.preview", {"query": prompt}
    if any(
        word in text
        for word in ["warehouse detail", "warehouse settings", "仓库详情", "倉庫詳情"]
    ):
        return "settings.warehouse.get", {"query": prompt}
    if any(word in text for word in ["sku list", "list sku", "skus", "product master", "商品"]):
        return "skus.list", {"query": prompt, "limit": 8}
    if any(word in text for word in ["inventory", "sku", "stock", "庫存", "查庫存"]):
        return "inventory.search", {"query": prompt, "limit": 8}
    if any(word in text for word in ["client", "customer", "客戶", "客户"]):
        return "clients.list", {"query": prompt, "limit": 8}
    if any(word in text for word in ["inbound", "receiving", "入庫", "入库"]):
        return "orders.inbound.list", {"limit": 8}
    if any(word in text for word in ["outbound", "shipping", "order", "出庫", "出库"]):
        return "orders.outbound.list", {"limit": 8}
    if any(word in text for word in ["billing", "rate", "charge", "費率", "计费", "計費"]):
        if "preview" in text or "预览" in text or "預覽" in text:
            return "settings.billing_rate_card.preview", {"limit": 8}
        return "billing.rate_cards.list", {"limit": 8}
    if any(word in text for word in ["warehouse", "倉庫", "仓库"]):
        return "warehouses.list", {"limit": 8}
    if any(word in text for word in ["setup", "配置", "設定", "设置"]):
        return "setup.progress", {}
    return None, {}


def route_read_request(prompt: str) -> ReadRoute:
    tool_name, args = route_prompt(prompt)
    if not tool_name:
        tool_name = "setup.progress"
        args = {}
    labels = {
        "settings.agent.get": "agent settings",
        "settings.receiving_codes.get": "receiving code settings",
        "settings.receiving_labels.get": "receiving label settings",
        "settings.users.list": "user settings",
        "settings.users.get": "user detail settings",
        "settings.permissions.explain": "permission settings",
        "settings.client_profile.get": "client profile settings",
        "settings.client_profile.preview": "client profile preview",
        "settings.billing.explain": "billing settings",
        "settings.warehouse_locations.list": "warehouse location settings",
        "settings.warehouse.get": "warehouse detail settings",
        "settings.rate_card.get": "rate card detail settings",
        "settings.receiving_codes.preview": "receiving code settings preview",
        "settings.receiving_labels.preview": "receiving label settings preview",
        "settings.sku.preview": "SKU settings preview",
        "settings.warehouse_location.preview": "warehouse location preview",
        "warehouse.blueprint.preview": "warehouse blueprint preview",
        "settings.billing_rate_card.preview": "billing rate card preview",
        "inventory.search": "inventory search",
        "clients.list": "client list",
        "orders.inbound.list": "inbound order list",
        "orders.outbound.list": "outbound order list",
        "billing.rate_cards.list": "billing rate card list",
        "warehouses.list": "warehouse list",
        "skus.list": "SKU master list",
        "setup.progress": "setup progress",
    }
    return ReadRoute(tool_name=tool_name, args=args, label=labels.get(tool_name, tool_name))
