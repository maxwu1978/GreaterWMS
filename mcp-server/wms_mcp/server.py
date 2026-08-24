"""MCP server for MaxSmart WMS.

Exposes the WMS to any MCP client (Claude Desktop, Claude Code, ...) while
preserving the platform's governance model:

- Authenticated calls use a real WMS account's bearer token (login happens
  lazily with WMS_EMAIL / WMS_PASSWORD; the MCP layer adds no privileges —
  you can do exactly what that account can do in the UI).
- Agent tools go through the governed /agent/tools/run endpoint: risk tiers,
  the allowed-tools whitelist, preview/confirm tokens for writes, and the
  evidence audit trail all apply unchanged.
- Tenant onboarding uses the same public registration endpoint as the sign-up
  page, including its explicit terms/risk-notice consent flags.

Configuration (environment variables):
    WMS_API_BASE_URL   default https://api.maxsmartwms.online/api/v1
    WMS_EMAIL          WMS account email (for authenticated tools)
    WMS_PASSWORD       WMS account password
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server import MCPServer

BASE_URL = os.environ.get("WMS_API_BASE_URL", "https://api.maxsmartwms.online/api/v1").rstrip("/")

mcp = MCPServer(
    "wms",
    instructions=(
        "MaxSmart WMS operations. Read tools run directly. Governed write tools are "
        "two-phase: the first run_agent_tool call returns a dry-run preview with a "
        "confirmation_token; show the preview to the user, and only after they approve "
        "call the tool again with confirmation_token merged into args."
    ),
)

_token: str | None = None


class WmsError(RuntimeError):
    pass


async def _login(client: httpx.AsyncClient) -> str:
    email = os.environ.get("WMS_EMAIL", "")
    password = os.environ.get("WMS_PASSWORD", "")
    if not email or not password:
        raise WmsError(
            "WMS_EMAIL / WMS_PASSWORD are not configured. Set them in the MCP server "
            "environment to use authenticated tools (register_tenant works without them)."
        )
    resp = await client.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code >= 400:
        raise WmsError(f"WMS login failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["access_token"]


async def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    authenticated: bool = True,
) -> Any:
    """One WMS API call with lazy login and a single re-login retry on 401."""
    global _token
    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in (1, 2):
            headers = {}
            if authenticated:
                if _token is None:
                    _token = await _login(client)
                headers["Authorization"] = f"Bearer {_token}"
            resp = await client.request(method, f"{BASE_URL}{path}", json=json, params=params, headers=headers)
            if resp.status_code == 401 and authenticated and attempt == 1:
                _token = None  # token expired — re-login once
                continue
            if resp.status_code >= 400:
                raise WmsError(f"WMS API {method} {path} failed ({resp.status_code}): {resp.text[:500]}")
            return resp.json() if resp.content else {}
    raise WmsError("unreachable")


@mcp.tool()
async def whoami() -> dict:
    """Verify the configured WMS account: login and report role, tenant, and permissions.

    Use this first to confirm the MCP server is wired to the right account.
    """
    global _token
    async with httpx.AsyncClient(timeout=30) as client:
        _token = await _login(client)
    settings = await _request("GET", "/agent/settings")
    return {
        "api_base_url": BASE_URL,
        "login": "ok",
        "agent_enabled": settings.get("enabled"),
        "allowed_agent_tools": settings.get("allowed_tools", []),
    }


@mcp.tool()
async def register_tenant(
    company_name: str,
    company_code: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
    accept_terms: bool,
    accept_risk_notice: bool,
    plan_code: str = "starter",
) -> dict:
    """Open a new WMS company workspace (tenant) with its admin account.

    This is real account opening — it calls the same public registration endpoint
    as the sign-up page. accept_terms and accept_risk_notice must be explicitly
    true and represent the END USER's consent: ask the human before calling.
    Depending on server config, the admin may need to verify their email and/or
    wait for a platform administrator to approve the workspace before first
    login (the response then carries pending_approval: true).
    """
    if not (accept_terms and accept_risk_notice):
        raise WmsError(
            "Registration requires explicit user consent: accept_terms and "
            "accept_risk_notice must both be true (ask the user, do not assume)."
        )
    return await _request(
        "POST",
        "/subscriptions/register",
        authenticated=False,
        json={
            "company_name": company_name,
            "company_code": company_code,
            "admin_email": admin_email,
            "admin_password": admin_password,
            "admin_name": admin_name,
            "plan_code": plan_code,
            "accept_terms": accept_terms,
            "accept_risk_notice": accept_risk_notice,
        },
    )


@mcp.tool()
async def create_client(
    name: str,
    code: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    billing_enabled: bool = True,
    portal_access: bool = True,
) -> dict:
    """Create a client (cargo owner) profile in the current tenant — 客户开户.

    Uses the standard REST endpoint with the configured account's own authority
    (requires master-data permission, i.e. a tenant admin account). The client
    code must be unique within the tenant — the database enforces this.
    """
    return await _request(
        "POST",
        "/clients/",
        json={
            "name": name,
            "code": code,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "billing_enabled": billing_enabled,
            "portal_access": portal_access,
        },
    )


@mcp.tool()
async def list_agent_tools() -> dict:
    """List the governed agent tool catalog: every tool key, its risk tier, and which are enabled for this tenant."""
    settings = await _request("GET", "/agent/settings")
    return {
        "enabled": settings.get("enabled"),
        "requires_human_confirmation_for_writes": settings.get(
            "requires_human_confirmation_for_writes"
        ),
        "allowed_tools": settings.get("allowed_tools", []),
        "tool_catalog": settings.get("tool_catalog", []),
    }


@mcp.tool()
async def run_agent_tool(tool_name: str, args: dict | None = None) -> dict:
    """Run a governed WMS agent tool (the same engine behind the in-app Agent Console).

    Every call is risk-tiered, whitelist-checked, and audit-logged server-side.
    Read tools (e.g. inventory.search {query, limit}, clients.list, skus.list,
    warehouses.list, orders.inbound.list, setup.progress) return data directly.

    WRITE tools are two-phase: the first call returns a DRY-RUN preview containing
    confirmation_payload.confirmation_token. Show that preview to the human; only
    after they approve, call again with the SAME args plus
    {"confirmation_token": "<token>"} to execute. Never invent or reuse tokens —
    they are bound to the exact previewed payload and expire.
    """
    return await _request(
        "POST", "/agent/tools/run", json={"tool_name": tool_name, "args": args or {}}
    )


@mcp.tool()
async def search_inventory(query: str = "", limit: int = 10) -> dict:
    """Search live inventory (governed read tool). Query matches SKU codes/names, clients, locations, warehouses, LPNs, lots."""
    return await _request(
        "POST",
        "/agent/tools/run",
        json={"tool_name": "inventory.search", "args": {"query": query, "limit": limit}},
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
