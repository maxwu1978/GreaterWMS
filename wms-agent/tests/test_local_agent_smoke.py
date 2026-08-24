from pathlib import Path

from fastapi.testclient import TestClient

from local_agent import server
from local_agent.audit import AuditLog


def _reset_server(tmp_path: Path) -> None:
    server.sessions._sessions.clear()
    server.sessions._default_session = None
    server.audit = AuditLog(tmp_path / "audit.jsonl")


async def _fake_login(self, email: str, password: str) -> dict:
    assert email == "operator@example.com"
    assert password == "secret"
    return {
        "access_token": "wms-token-secret",
        "role": "tenant_admin",
        "tenant_id": "tenant-1",
        "job_title": "Ops",
        "permissions": ["master_data.manage"],
    }


async def _fake_settings(self) -> dict:
    return {
        "enabled": True,
        "allowed_tools": ["inventory.search", "clients.list"],
        "tool_catalog": [
            {"key": "inventory.search", "risk": "low", "description": "Search stock."},
            {"key": "clients.list", "risk": "low", "description": "List clients."},
        ],
    }


async def _fake_run_tool(self, token_or_tool_name, tool_name_or_args=None, args=None) -> dict:
    tool_name = token_or_tool_name
    if isinstance(tool_name_or_args, str):
        tool_name = tool_name_or_args
    return {
        "ok": True,
        "tool_name": tool_name,
        "risk": "low",
        "result": {"rows": [{"sku": "SKU-1"}]},
    }


async def _fake_post(self, path: str, body: dict, headers: dict | None = None) -> dict:
    return {
        "ok": True,
        "path": path,
        "body": body,
        "idempotency_key": (headers or {}).get("X-Idempotency-Key"),
    }


class _FakeModelAdapter:
    async def plan(self, **kwargs) -> dict:
        return {
            "enabled": False,
            "suggested_tool": None,
            "suggested_args": {},
            "needs_confirmation": False,
        }


async def _fake_compare_model_plans(**kwargs) -> list[dict]:
    return [
        {
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-chat",
            "suggested_tool": "receiving.inbound.import_with_mapping",
            "suggested_args": {},
            "needs_confirmation": True,
            "confidence": 0.8,
        },
        {
            "enabled": True,
            "provider": "qwen",
            "model": "qwen-max",
            "suggested_tool": "inventory.search",
            "suggested_args": {"query": "SKU-1"},
            "needs_confirmation": False,
            "confidence": 0.7,
        },
    ]


def test_local_agent_smoke_login_read_block_confirm_and_audit(monkeypatch, tmp_path: Path) -> None:
    _reset_server(tmp_path)
    monkeypatch.setattr(server.WmsClient, "login", _fake_login)
    monkeypatch.setattr(server.WmsClient, "get_agent_settings", _fake_settings)
    monkeypatch.setattr(server.WmsClient, "run_tool", _fake_run_tool)
    monkeypatch.setattr(server.WmsClient, "post", _fake_post)
    monkeypatch.setattr(server, "_model_adapter", lambda: _FakeModelAdapter())

    client = TestClient(server.app)

    config = client.get("/api/config")
    assert config.status_code == 200
    assert {item["key"] for item in config.json()["model_roster"]} == {
        "minimax",
        "qwen",
        "kimi",
        "deepseek",
    }
    assert "api_key" not in str(config.json()).lower()

    missing = client.post("/api/chat", json={"session_id": "missing", "prompt": "inventory"})
    assert missing.status_code == 401

    login = client.post(
        "/api/session/login",
        json={
            "wms_api_base_url": "https://api.example.com",
            "email": "operator@example.com",
            "password": "secret",
        },
    )
    assert login.status_code == 200
    session_id = login.json()["session_id"]
    assert login.json()["allowed_tools"] == ["inventory.search", "clients.list"]

    read = client.post(
        "/api/chat",
        json={"session_id": session_id, "prompt": "show inventory for SKU-1"},
    )
    assert read.status_code == 200
    assert read.json()["tool_result"]["tool_name"] == "inventory.search"

    explicit_block = client.post(
        "/api/tools/run",
        json={"session_id": session_id, "tool_name": "warehouses.list", "args": {}},
    )
    assert explicit_block.status_code == 403
    assert "not enabled" in explicit_block.json()["detail"]

    chat_block = client.post(
        "/api/chat",
        json={"session_id": session_id, "prompt": "List warehouses"},
    )
    assert chat_block.status_code == 403
    assert "not enabled" in chat_block.json()["detail"]

    blocked = client.post(
        "/api/chat",
        json={"session_id": session_id, "prompt": "confirm inventory adjustment"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["blocked"] is True
    assert blocked.json()["confirmation_required"] is True

    rejected = client.post(
        "/api/confirm",
        json={"session_id": session_id, "preview_payload": {"ok": True}},
    )
    assert rejected.status_code == 409

    preview = {
        "confirmation_required_for_write": True,
        "action": "inventory.adjust",
        "risk": "medium",
        "planned_request": {
            "endpoint": "POST /api/v1/inventory/ops/adjust/preview",
            "body": {"inventory_id": "inv-1", "new_quantity": 5, "reason": "Count"},
        },
        "confirmation_payload": {
            "confirmation_token": "inv-adjust:secret",
            "evidence_id": "ev-1",
        },
    }
    confirmed = client.post(
        "/api/confirm",
        json={"session_id": session_id, "preview_payload": preview, "idempotency_key": "idem-1"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["result"]["path"] == "/inventory/ops/adjust/agent"
    assert confirmed.json()["result"]["body"]["confirmation_token"] == "inv-adjust:secret"

    high_risk_preview = {
        "confirmation_required_for_write": True,
        "action": "settings.billing_rate_card.update",
        "risk": "high",
        "planned_request": {
            "endpoint": "POST /api/v1/agent/settings/billing-rate-card/preview",
            "body": {"rate_card_id": "rate-1", "changes": {"pick_fee": 2.5}},
        },
        "confirmation_payload": {
            "confirmation_token": "billing-rate:secret",
            "evidence_id": "ev-high-1",
        },
    }
    missing_strong_confirmation = client.post(
        "/api/confirm",
        json={
            "session_id": session_id,
            "preview_payload": high_risk_preview,
            "idempotency_key": "idem-high-1",
        },
    )
    assert missing_strong_confirmation.status_code == 409
    assert "Strong confirmation" in missing_strong_confirmation.json()["detail"]

    high_risk_confirmed = client.post(
        "/api/confirm",
        json={
            "session_id": session_id,
            "preview_payload": high_risk_preview,
            "idempotency_key": "idem-high-1",
            "strong_confirmation": "ev-high-1",
        },
    )
    assert high_risk_confirmed.status_code == 200
    assert high_risk_confirmed.json()["result"]["path"] == (
        "/agent/settings/billing-rate-card/agent"
    )

    server.audit.append(
        "redaction_probe",
        {
            "access_token": "wms-token-secret",
            "api_key": "model-secret",
            "nested": {"secret": "hidden"},
        },
    )

    audit = client.get("/api/audit?limit=20")
    assert audit.status_code == 200
    serialized = str(audit.json())
    assert "wms-token-secret" not in serialized
    assert "inv-adjust:secret" not in serialized
    assert "model-secret" not in serialized
    assert "hidden" not in serialized
    assert "[redacted]" in serialized


def test_local_agent_planner_comparison_is_local_only_and_policy_adjudicated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _reset_server(tmp_path)

    async def fake_settings_with_direct_write(self) -> dict:
        settings = await _fake_settings(self)
        settings["allowed_tools"] = [
            "inventory.search",
            "receiving.inbound.import_with_mapping",
        ]
        settings["tool_catalog"].append(
            {
                "key": "receiving.inbound.import_with_mapping",
                "risk": "medium",
                "description": "Direct import write.",
            }
        )
        return settings

    monkeypatch.setattr(server.WmsClient, "login", _fake_login)
    monkeypatch.setattr(server.WmsClient, "get_agent_settings", fake_settings_with_direct_write)
    monkeypatch.setattr(server, "_model_configs", lambda: [])
    monkeypatch.setattr(server, "compare_model_plans", _fake_compare_model_plans)

    client = TestClient(server.app)

    unauthenticated = client.post(
        "/api/plans/compare",
        json={"session_id": "missing", "prompt": "show stock and import inventory"},
    )
    assert unauthenticated.status_code == 401

    login = client.post(
        "/api/session/login",
        json={
            "wms_api_base_url": "https://api.example.com",
            "email": "operator@example.com",
            "password": "secret",
        },
    )
    assert login.status_code == 200
    session_id = login.json()["session_id"]

    compared = client.post(
        "/api/plans/compare",
        json={"session_id": session_id, "prompt": "deepseek local agent inventory SKU-1"},
    )

    assert compared.status_code == 200
    payload = compared.json()
    assert payload["adjudication"]["selected_provider"] == "qwen"
    assert payload["adjudication"]["selected_tool"] == "inventory.search"
    assert payload["adjudication"]["rejected"][0]["provider"] == "deepseek"
    assert "direct write" in payload["adjudication"]["rejected"][0]["reason"]
    selected_skill_names = {skill["name"] for skill in payload["selected_skills"]}
    assert "wms-local-agent-operator" in selected_skill_names
    assert all("reasons" in skill for skill in payload["selected_skills"])

    audit = client.get("/api/audit?limit=20")
    serialized = str(audit.json())
    assert "planner_comparison" in serialized
    assert "wms-token-secret" not in serialized
    assert "secret" not in serialized


def test_local_agent_evidence_detail_uses_active_session_and_propagates_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _reset_server(tmp_path)
    calls = []

    async def fake_get_evidence_detail(self, evidence_id: str) -> dict:
        calls.append({"evidence_id": evidence_id, "token": self.token})
        if evidence_id == "ev-missing":
            raise server.WmsApiError(404, "Evidence not found")
        if evidence_id == "ev-failed":
            raise server.WmsApiError(500, "WMS evidence lookup failed")
        return {
            "id": evidence_id,
            "tool_name": "inventory.adjust",
            "eligible_for_replay": True,
        }

    monkeypatch.setattr(server.WmsClient, "login", _fake_login)
    monkeypatch.setattr(server.WmsClient, "get_agent_settings", _fake_settings)
    monkeypatch.setattr(server.WmsClient, "get_evidence_detail", fake_get_evidence_detail)

    client = TestClient(server.app)

    unauthenticated = client.get("/api/evidence/ev-1")
    assert unauthenticated.status_code == 401

    login = client.post(
        "/api/session/login",
        json={
            "wms_api_base_url": "https://api.example.com",
            "email": "operator@example.com",
            "password": "secret",
        },
    )
    assert login.status_code == 200

    found = client.get("/api/evidence/ev-1")
    assert found.status_code == 200
    assert found.json() == {
        "ok": True,
        "evidence": {
            "id": "ev-1",
            "tool_name": "inventory.adjust",
            "eligible_for_replay": True,
        },
    }
    assert calls[-1] == {"evidence_id": "ev-1", "token": "wms-token-secret"}

    missing = client.get("/api/evidence/ev-missing")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Evidence not found"

    failed = client.get("/api/evidence/ev-failed")
    assert failed.status_code == 500
    assert failed.json()["detail"] == "WMS evidence lookup failed"

    audit = client.get("/api/audit?limit=20")
    assert audit.status_code == 200
    serialized = str(audit.json())
    assert "ev-1" in serialized
    assert "wms-token-secret" not in serialized


def test_local_agent_evidence_replay_preview_and_failed_use_active_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _reset_server(tmp_path)
    calls = []

    async def fake_get_evidence_replay_preview(self, evidence_id: str) -> dict:
        calls.append(
            {
                "method": "replay_preview",
                "evidence_id": evidence_id,
                "token": self.token,
            }
        )
        if evidence_id == "ev-not-eligible":
            raise server.WmsApiError(409, "Evidence is not replay eligible")
        return {
            "evidence_id": evidence_id,
            "eligible_for_replay": True,
            "planned_request": {"endpoint": "POST /api/v1/inventory/ops/adjust/agent"},
            "confirmation_payload": {"confirmation_token": "replay-confirm-secret"},
        }

    async def fake_get_failed_evidence(self) -> dict:
        calls.append({"method": "failed", "token": self.token})
        return {
            "items": [
                {
                    "id": "ev-failed-1",
                    "tool_name": "inventory.adjust",
                    "status": "failed",
                }
            ]
        }

    monkeypatch.setattr(server.WmsClient, "login", _fake_login)
    monkeypatch.setattr(server.WmsClient, "get_agent_settings", _fake_settings)
    monkeypatch.setattr(
        server.WmsClient,
        "get_evidence_replay_preview",
        fake_get_evidence_replay_preview,
    )
    monkeypatch.setattr(server.WmsClient, "get_failed_evidence", fake_get_failed_evidence)

    client = TestClient(server.app)

    unauthenticated_replay = client.get("/api/evidence/ev-1/replay-preview")
    assert unauthenticated_replay.status_code == 401

    unauthenticated_failed = client.get("/api/evidence/failed")
    assert unauthenticated_failed.status_code == 401

    login = client.post(
        "/api/session/login",
        json={
            "wms_api_base_url": "https://api.example.com",
            "email": "operator@example.com",
            "password": "secret",
        },
    )
    assert login.status_code == 200
    session_id = login.json()["session_id"]

    replay = client.get(f"/api/evidence/ev-1/replay-preview?session_id={session_id}")
    assert replay.status_code == 200
    assert replay.json()["replay_preview"]["eligible_for_replay"] is True
    assert calls[-1] == {
        "method": "replay_preview",
        "evidence_id": "ev-1",
        "token": "wms-token-secret",
    }

    failed = client.get(f"/api/evidence/failed?session_id={session_id}")
    assert failed.status_code == 200
    assert failed.json()["failed_evidence"]["items"][0]["id"] == "ev-failed-1"
    assert calls[-1] == {"method": "failed", "token": "wms-token-secret"}

    not_eligible = client.get(
        f"/api/evidence/ev-not-eligible/replay-preview?session_id={session_id}"
    )
    assert not_eligible.status_code == 409
    assert not_eligible.json()["detail"] == "Evidence is not replay eligible"

    audit = client.get("/api/audit?limit=20")
    assert audit.status_code == 200
    serialized = str(audit.json())
    assert "evidence_replay_preview" in serialized
    assert "evidence_failed" in serialized
    assert "ev-1" in serialized
    assert "wms-token-secret" not in serialized
    assert "replay-confirm-secret" not in serialized
