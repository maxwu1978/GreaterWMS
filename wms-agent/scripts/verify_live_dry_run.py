"""Optional live dry-run verifier for the local WMS agent.

This script is safe by default: without LOCAL_AGENT_TEST_EMAIL and
LOCAL_AGENT_TEST_PASSWORD it only verifies that live checks are skipped.
"""

from __future__ import annotations

import asyncio
import json
import os

from local_agent.config import normalize_wms_api_url
from local_agent.confirmation import build_confirmation_request
from local_agent.wms_client import WmsClient


async def main() -> int:
    api_url = normalize_wms_api_url(
        os.getenv("LOCAL_AGENT_TEST_API_URL", "https://api.maxsmartwms.online")
    )
    email = os.getenv("LOCAL_AGENT_TEST_EMAIL")
    password = os.getenv("LOCAL_AGENT_TEST_PASSWORD")
    evidence: dict = {
        "ok": True,
        "action": "local_agent.live_dry_run",
        "api_url": api_url,
        "skipped": not (email and password),
        "checks": {},
    }
    if not (email and password):
        evidence["checks"]["credentials"] = "missing; live dry-run skipped"
        print(json.dumps(evidence, indent=2))
        return 0

    token = await WmsClient(api_url).login(email, password)
    client = WmsClient(api_url, token["access_token"])
    settings = await client.get_agent_settings()
    evidence["checks"]["settings"] = {
        "enabled": settings.get("enabled"),
        "allowed_tool_count": len(settings.get("allowed_tools") or []),
    }

    for tool_name, args in [
        ("inventory.search", {"query": "SKU", "limit": 1}),
        ("clients.list", {"limit": 1}),
        ("orders.inbound.list", {"limit": 1}),
        ("orders.outbound.list", {"limit": 1}),
    ]:
        try:
            result = await client.run_tool(tool_name, args)
            evidence["checks"][tool_name] = {"ok": result.get("ok", True), "tool_name": tool_name}
        except Exception as exc:  # noqa: BLE001 - evidence should capture all live failures.
            evidence["ok"] = False
            evidence["checks"][tool_name] = {"ok": False, "error": str(exc)}

    for bad_payload in [{}, {"planned_request": {"endpoint": "GET /api/v1/x/preview"}}]:
        try:
            build_confirmation_request(bad_payload)
        except Exception as exc:  # noqa: BLE001 - expected rejection evidence.
            evidence["checks"].setdefault("confirmation_rejections", []).append(str(exc))
        else:
            evidence["ok"] = False
            evidence["checks"].setdefault("confirmation_rejections", []).append("unexpected accept")

    print(json.dumps(evidence, indent=2))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
