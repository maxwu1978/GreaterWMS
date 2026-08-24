"""Local policy checks for governed WMS tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DIRECT_WRITE_TOOLS = {
    "receiving.inbound.import_with_mapping",
    "orders.outbound.import_with_mapping",
    "migration.inventory.import",
    "clients.create",
    "skus.create",
    "receiving.inbound.create",
    "users.create",
    "users.update",
    "users.reset_password",
    "users.update_permissions",
}


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str | None = None
    risk: str | None = None


def allowed_tool_keys(agent_settings: dict[str, Any]) -> set[str]:
    return {str(tool) for tool in agent_settings.get("allowed_tools") or []}


def tool_catalog_by_key(agent_settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in agent_settings.get("tool_catalog") or []:
        key = item.get("key")
        if isinstance(key, str):
            catalog[key] = item
    return catalog


def decide_tool(agent_settings: dict[str, Any], tool_name: str) -> ToolDecision:
    if not tool_name:
        return ToolDecision(False, "No WMS tool was selected.")
    if tool_name not in allowed_tool_keys(agent_settings):
        return ToolDecision(False, f"Tool '{tool_name}' is not enabled for this session.")
    catalog = tool_catalog_by_key(agent_settings)
    risk = str((catalog.get(tool_name) or {}).get("risk") or "")
    if tool_name in DIRECT_WRITE_TOOLS:
        return ToolDecision(
            False,
            (
                f"Tool '{tool_name}' is a direct write tool. Run a WMS preview first, "
                "then confirm through /api/confirm with an evidence token."
            ),
            risk or None,
        )
    return ToolDecision(True, risk=risk or None)


def require_tool(agent_settings: dict[str, Any], tool_name: str) -> ToolDecision:
    decision = decide_tool(agent_settings, tool_name)
    if not decision.allowed:
        return decision
    return decision
