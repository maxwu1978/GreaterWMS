import asyncio
from pathlib import Path

import httpx
import pytest

from local_agent.audit import redact
from local_agent.config import (
    LocalAgentSettings,
    backend_model_configs,
    backend_model_roster,
    normalize_wms_api_url,
    read_env_file,
)
from local_agent.confirmation import (
    ConfirmationError,
    build_confirmation_request,
    extract_confirmation_card,
    requires_strong_confirmation,
)
from local_agent.model_adapter import ModelAdapter, ModelConfig, _parse_plan
from local_agent.policy import DIRECT_WRITE_TOOLS, decide_tool
from local_agent.router import route_prompt
from local_agent.session import LocalSession
from local_agent.skills import Skill, SkillRegistry
from local_agent.wms_client import WmsApiError, WmsClient


def test_redact_removes_secrets() -> None:
    payload = {
        "access_token": "secret",
        "nested": {"confirmation_token": "confirm", "value": "safe"},
    }

    assert redact(payload) == {
        "access_token": "[redacted]",
        "nested": {"confirmation_token": "[redacted]", "value": "safe"},
    }


def test_router_blocks_write_terms_and_routes_reads() -> None:
    assert route_prompt("show clients") == ("clients.list", {"query": "show clients", "limit": 8})
    assert route_prompt("show outbound orders") == ("orders.outbound.list", {"limit": 8})
    assert route_prompt("show inventory for SKU-001") == (
        "inventory.search",
        {"query": "show inventory for SKU-001", "limit": 8},
    )
    assert route_prompt("show users and permissions") == ("settings.permissions.explain", {})
    assert route_prompt("show receiving code settings") == ("settings.receiving_codes.get", {})
    assert route_prompt("preview receiving code settings") == (
        "settings.receiving_codes.preview",
        {},
    )
    assert route_prompt("show warehouse locations") == (
        "settings.warehouse_locations.list",
        {"limit": 25},
    )
    assert route_prompt("preview warehouse location change") == (
        "settings.warehouse_location.preview",
        {"limit": 25},
    )
    assert route_prompt("billing rate card preview") == (
        "settings.billing_rate_card.preview",
        {"limit": 8},
    )
    assert route_prompt("turn the lights on") == (None, {})


def test_normalize_wms_api_url() -> None:
    assert normalize_wms_api_url("https://api.example.com") == "https://api.example.com/api/v1"
    assert normalize_wms_api_url("https://api.example.com/api") == "https://api.example.com/api/v1"
    assert normalize_wms_api_url("https://api.example.com/api/v1") == "https://api.example.com/api/v1"


@pytest.mark.asyncio
async def test_wms_client_get_evidence_detail_uses_authenticated_agent_endpoint(
    monkeypatch,
) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            calls.append({"url": url, "headers": headers})
            return httpx.Response(
                200,
                json={"id": "ev/1", "eligible_for_replay": False},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("local_agent.wms_client.httpx.AsyncClient", FakeClient)

    result = await WmsClient("https://api.example.com", "wms-token-secret").get_evidence_detail(
        "ev/1",
    )

    assert result == {"id": "ev/1", "eligible_for_replay": False}
    assert calls == [
        {
            "url": "https://api.example.com/api/v1/agent/evidence/ev%2F1",
            "headers": {"Authorization": "Bearer wms-token-secret"},
        }
    ]


@pytest.mark.asyncio
async def test_wms_client_get_evidence_detail_maps_missing_and_failed_responses(
    monkeypatch,
) -> None:
    responses = [
        httpx.Response(
            404,
            json={"detail": "Evidence not found"},
            request=httpx.Request(
                "GET",
                "https://api.example.com/api/v1/agent/evidence/ev-missing",
            ),
        ),
        httpx.Response(
            500,
            json={"detail": "Evidence lookup failed"},
            request=httpx.Request(
                "GET",
                "https://api.example.com/api/v1/agent/evidence/ev-failed",
            ),
        ),
    ]

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            return responses.pop(0)

    monkeypatch.setattr("local_agent.wms_client.httpx.AsyncClient", FakeClient)
    client = WmsClient("https://api.example.com", "wms-token-secret")

    with pytest.raises(WmsApiError) as missing:
        await client.get_evidence_detail("ev-missing")
    assert missing.value.status_code == 404
    assert missing.value.detail == "Evidence not found"

    with pytest.raises(WmsApiError) as failed:
        await client.get_evidence_detail("ev-failed")
    assert failed.value.status_code == 500
    assert failed.value.detail == "Evidence lookup failed"


@pytest.mark.asyncio
async def test_wms_client_get_evidence_replay_preview_uses_authenticated_agent_endpoint(
    monkeypatch,
) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            calls.append({"url": url, "headers": headers})
            return httpx.Response(
                200,
                json={"ok": True, "evidence_id": "ev/1", "eligible_for_replay": True},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("local_agent.wms_client.httpx.AsyncClient", FakeClient)

    result = await WmsClient(
        "https://api.example.com",
        "wms-token-secret",
    ).get_evidence_replay_preview("ev/1")

    assert result == {"ok": True, "evidence_id": "ev/1", "eligible_for_replay": True}
    assert calls == [
        {
            "url": "https://api.example.com/api/v1/agent/evidence/ev%2F1/replay-preview",
            "headers": {"Authorization": "Bearer wms-token-secret"},
        }
    ]


@pytest.mark.asyncio
async def test_wms_client_get_failed_evidence_uses_authenticated_agent_endpoint(
    monkeypatch,
) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            calls.append({"url": url, "headers": headers})
            return httpx.Response(
                200,
                json={"items": [{"id": "ev-failed-1", "status": "failed"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("local_agent.wms_client.httpx.AsyncClient", FakeClient)

    result = await WmsClient("https://api.example.com", "wms-token-secret").get_failed_evidence()

    assert result == {"items": [{"id": "ev-failed-1", "status": "failed"}]}
    assert calls == [
        {
            "url": "https://api.example.com/api/v1/agent/evidence/failed",
            "headers": {"Authorization": "Bearer wms-token-secret"},
        }
    ]


@pytest.mark.asyncio
async def test_wms_client_new_evidence_endpoints_map_error_responses(monkeypatch) -> None:
    responses = [
        httpx.Response(
            409,
            json={"detail": "Evidence is not replay eligible"},
            request=httpx.Request(
                "GET",
                "https://api.example.com/api/v1/agent/evidence/ev-1/replay-preview",
            ),
        ),
        httpx.Response(
            503,
            json={"detail": "Failed evidence unavailable"},
            request=httpx.Request(
                "GET",
                "https://api.example.com/api/v1/agent/evidence/failed",
            ),
        ),
    ]

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            return responses.pop(0)

    monkeypatch.setattr("local_agent.wms_client.httpx.AsyncClient", FakeClient)
    client = WmsClient("https://api.example.com", "wms-token-secret")

    with pytest.raises(WmsApiError) as replay:
        await client.get_evidence_replay_preview("ev-1")
    assert replay.value.status_code == 409
    assert replay.value.detail == "Evidence is not replay eligible"

    with pytest.raises(WmsApiError) as failed:
        await client.get_failed_evidence()
    assert failed.value.status_code == 503
    assert failed.value.detail == "Failed evidence unavailable"


def test_read_env_file_strips_quotes(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'DEEPSEEK_API_KEY="secret-value"\nDEEPSEEK_MODEL=deepseek-v4-flash\n',
        encoding="utf-8",
    )

    values = read_env_file(env_path)

    assert values["DEEPSEEK_API_KEY"] == "secret-value"
    assert values["DEEPSEEK_MODEL"] == "deepseek-v4-flash"


def test_backend_model_roster_reports_configured_providers_without_secrets() -> None:
    roster = backend_model_roster(
        {
            "QWEN_API_KEY": "qwen-secret",
            "QWEN_MODEL": "qwen-plus",
            "KIMI_API_KEY": "",
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }
    )

    by_key = {item["key"]: item for item in roster}

    assert by_key["qwen"]["configured"] is True
    assert by_key["qwen"]["model"] == "qwen-plus"
    assert by_key["kimi"]["configured"] is False
    assert by_key["deepseek"]["configured"] is True
    assert "qwen-secret" not in str(roster)
    assert "deepseek-secret" not in str(roster)


def test_backend_model_configs_are_internal_and_ordered() -> None:
    configs = backend_model_configs(
        {
            "QWEN_API_KEY": "qwen-secret",
            "QWEN_MODEL": "qwen-plus",
            "DEEPSEEK_API_KEY": "deepseek-secret",
            "DEEPSEEK_MODEL": "deepseek-chat",
        }
    )

    assert [config["provider"] for config in configs] == ["deepseek", "qwen"]
    assert configs[0]["api_key"] == "deepseek-secret"


def test_local_agent_prefers_requested_backend_provider(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    backend_dir = repo / "backend"
    backend_dir.mkdir(parents=True)
    (backend_dir / ".env").write_text(
        "QWEN_API_KEY=qwen-secret\n"
        "QWEN_MODEL=qwen-plus\n"
        "KIMI_API_KEY=kimi-secret\n"
        "KIMI_MODEL=moonshot-v1-8k\n"
        "DEEPSEEK_API_KEY=deepseek-secret\n"
        "DEEPSEEK_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("local_agent.config.repo_root", lambda: repo)

    settings = LocalAgentSettings(model_provider="qwen")

    assert settings.effective_model_provider == "qwen"
    assert settings.effective_model_name == "qwen-plus"
    assert settings.effective_model_api_key == "qwen-secret"
    assert settings.effective_model_source == "agent env"


def test_local_agent_uses_direct_deepseek_env() -> None:
    settings = LocalAgentSettings(
        model_provider="deepseek",
        model_base_url="https://api.deepseek.com/v1",
        model_name="deepseek-chat",
        model_api_key="deepseek-secret",
    )

    assert settings.effective_model_provider == "deepseek"
    assert settings.effective_model_base_url == "https://api.deepseek.com/v1"
    assert settings.effective_model_name == "deepseek-chat"
    assert settings.effective_model_api_key == "deepseek-secret"
    assert settings.effective_model_source == "local-agent env"


def test_policy_blocks_disallowed_and_direct_write_tools() -> None:
    settings = {
        "allowed_tools": [
            "inventory.search",
            "receiving.inbound.import_with_mapping",
        ],
        "tool_catalog": [
            {"key": "inventory.search", "risk": "low"},
            {"key": "receiving.inbound.import_with_mapping", "risk": "medium"},
        ],
    }

    assert decide_tool(settings, "inventory.search").allowed is True
    disallowed = decide_tool(settings, "warehouses.list")
    assert disallowed.allowed is False
    assert "not enabled" in disallowed.reason
    direct_write = decide_tool(settings, "receiving.inbound.import_with_mapping")
    assert direct_write.allowed is False
    assert direct_write.risk == "medium"
    assert "direct write" in direct_write.reason
    assert "migration.inventory.import" in DIRECT_WRITE_TOOLS


def test_skill_registry_selects_relevant_wms_skill(tmp_path: Path) -> None:
    skill_dir = tmp_path / "wms-inventory-operator"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# WMS Inventory Operator\nUse inventory tools.",
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path)
    selected = registry.select("show stock for this SKU")

    assert [skill.name for skill in selected] == ["wms-inventory-operator"]


def test_skill_registry_selects_local_agent_operator(tmp_path: Path) -> None:
    skill_dir = tmp_path / "wms-local-agent-operator"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: wms-local-agent-operator\n"
        "description: Operate WMS through the local governed agent shell.\n"
        "---\n"
        "# WMS Local Agent Operator\n",
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path)
    selected = registry.select("use the local agent shell with audit checks")

    assert [skill.name for skill in selected] == ["wms-local-agent-operator"]


def test_skill_registry_explains_selection_without_skill_body(tmp_path: Path) -> None:
    skill_dir = tmp_path / "wms-local-agent-operator"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: wms-local-agent-operator\n"
        "description: Operate WMS through the local governed agent shell.\n"
        "---\n"
        "# WMS Local Agent Operator\nsecret-body\n",
        encoding="utf-8",
    )

    registry = SkillRegistry(tmp_path)
    matches = registry.explain_selection("deepseek local agent audit", limit=1)
    public = matches[0].to_public_dict()

    assert public["name"] == "wms-local-agent-operator"
    assert public["score"] >= 3
    assert "matched keyword: deepseek" in public["reasons"]
    assert "secret-body" not in str(public)


def test_model_prompt_does_not_include_wms_token_or_model_api_key() -> None:
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-secret-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=["master_data.manage"],
        agent_settings={
            "tool_catalog": [
                {
                    "key": "inventory.search",
                    "risk": "low",
                    "description": "Search inventory.",
                    "access_token": "bad",
                }
            ]
        },
    )
    adapter = ModelAdapter(
        ModelConfig(
            provider="deepseek",
            base_url="https://model.example.com/v1",
            model="deepseek-chat",
            api_key="model-secret-key",
        )
    )

    messages = adapter.build_messages(session=session, prompt="show inventory", selected_skills=[])
    serialized = str(messages)

    assert "wms-secret-token" not in serialized
    assert "model-secret-key" not in serialized
    assert "bad" not in serialized
    assert "inventory.search" in serialized


def test_model_prompt_keeps_skill_and_tool_context_public_only() -> None:
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-secret-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=["users.manage"],
        agent_settings={
            "tool_catalog": [
                {
                    "key": "settings.receiving_codes.preview",
                    "risk": "medium",
                    "description": "Preview receiving code settings.",
                    "api_key": "never-send",
                }
            ]
        },
    )
    adapter = ModelAdapter(ModelConfig(provider="deepseek"))

    messages = adapter.build_messages(
        session=session,
        prompt="preview receiving code settings",
        selected_skills=[
            Skill(
                name="wms-local-agent-operator",
                description="Operate WMS through local tools.",
                path="/tmp/SKILL.md",
                body="Use preview, evidence, and confirmation cards.",
            )
        ],
    )
    serialized = str(messages)

    assert "settings.receiving_codes.preview" in serialized
    assert "wms-local-agent-operator" in serialized
    assert "never-send" not in serialized
    assert "wms-secret-token" not in serialized


def test_model_plan_json_parser_extracts_suggested_tool() -> None:
    parsed = _parse_plan(
        '{"summary":"Use inventory lookup","tool_name":"inventory.search",'
        '"args":{"query":"SKU-1","limit":8},"needs_confirmation":false,'
        '"confidence":0.8}'
    )

    assert parsed["tool_name"] == "inventory.search"
    assert parsed["args"] == {"query": "SKU-1", "limit": 8}
    assert parsed["needs_confirmation"] is False


@pytest.mark.asyncio
async def test_model_adapter_retries_without_response_format(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}
            self.request = httpx.Request("POST", "https://model.example.com/chat/completions")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "bad request",
                    request=self.request,
                    response=httpx.Response(self.status_code, request=self.request),
                )

        def json(self) -> dict:
            return self._payload

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict):
            calls.append(json.copy())
            if len(calls) == 1:
                return FakeResponse(400)
            return FakeResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"summary":"ok","tool_name":"inventory.search",'
                                    '"args":{"query":"SKU"},"needs_confirmation":false}'
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr("local_agent.model_adapter.httpx.AsyncClient", FakeClient)
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=[],
        agent_settings={"tool_catalog": [{"key": "inventory.search", "risk": "low"}]},
    )
    adapter = ModelAdapter(
        ModelConfig(
            provider="openai-compatible",
            base_url="https://model.example.com",
            model="model",
            api_key="secret",
        )
    )

    plan = await adapter.plan(session=session, prompt="show inventory", selected_skills=[])

    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
    assert plan["suggested_tool"] == "inventory.search"


@pytest.mark.asyncio
async def test_model_adapter_can_plan_with_multiple_openai_compatible_providers(
    monkeypatch,
) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, headers: dict, json: dict):
            calls.append({"url": url, "headers": headers, "json": json})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"summary":"preview settings","tool_name":'
                                    '"settings.receiving_codes.preview","args":{},'
                                    '"needs_confirmation":true,"confidence":0.74}'
                                )
                            }
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("local_agent.model_adapter.httpx.AsyncClient", FakeClient)
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=["users.manage"],
        agent_settings={
            "tool_catalog": [{"key": "settings.receiving_codes.preview", "risk": "medium"}]
        },
    )

    providers = [
        ModelConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            api_key="deepseek-secret",
        ),
        ModelConfig(
            provider="qwen",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-max",
            api_key="qwen-secret",
        ),
    ]

    plans = [
        await ModelAdapter(config).plan(
            session=session,
            prompt="preview receiving code settings",
            selected_skills=[],
        )
        for config in providers
    ]

    assert [plan["provider"] for plan in plans] == ["deepseek", "qwen"]
    assert {plan["suggested_tool"] for plan in plans} == {"settings.receiving_codes.preview"}
    assert calls[0]["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert calls[1]["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert "deepseek-secret" not in str(plans)
    assert "qwen-secret" not in str(plans)


@pytest.mark.asyncio
async def test_compare_model_plans_runs_all_configured_providers(monkeypatch) -> None:
    from local_agent.model_adapter import compare_model_plans

    calls = []

    async def fake_plan(self, *, session, prompt, selected_skills):
        calls.append(self.config.provider)
        return {
            "enabled": True,
            "provider": self.config.provider,
            "model": self.config.model,
            "suggested_tool": "inventory.search",
            "suggested_args": {"query": prompt},
            "needs_confirmation": False,
        }

    monkeypatch.setattr(ModelAdapter, "plan", fake_plan)
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=[],
        agent_settings={"tool_catalog": [{"key": "inventory.search", "risk": "low"}]},
    )

    plans = await compare_model_plans(
        configs=[
            ModelConfig(provider="deepseek", model="deepseek-chat", api_key="secret"),
            ModelConfig(provider="qwen", model="qwen-max", api_key="secret"),
        ],
        session=session,
        prompt="SKU-1",
        selected_skills=[],
    )

    assert calls == ["deepseek", "qwen"]
    assert [plan["provider"] for plan in plans] == ["deepseek", "qwen"]
    assert "secret" not in str(plans)


@pytest.mark.asyncio
async def test_compare_model_plans_returns_timeout_result(monkeypatch) -> None:
    from local_agent.model_adapter import compare_model_plans

    async def slow_plan(self, *, session, prompt, selected_skills):
        await asyncio.sleep(0.1)
        return {
            "enabled": True,
            "provider": self.config.provider,
            "model": self.config.model,
            "suggested_tool": "inventory.search",
            "suggested_args": {"query": prompt},
            "needs_confirmation": False,
        }

    monkeypatch.setattr(ModelAdapter, "plan", slow_plan)
    session = LocalSession(
        id="session-1",
        wms_api_base_url="https://api.example.com/api/v1",
        access_token="wms-token",
        role="tenant_admin",
        tenant_id="tenant-1",
        job_title="Ops",
        permissions=[],
        agent_settings={"tool_catalog": [{"key": "inventory.search", "risk": "low"}]},
    )

    plans = await compare_model_plans(
        configs=[ModelConfig(provider="deepseek", model="deepseek-chat", api_key="secret")],
        session=session,
        prompt="SKU-1",
        selected_skills=[],
        timeout_seconds=0.01,
    )

    assert plans[0]["provider"] == "deepseek"
    assert plans[0]["suggested_tool"] is None
    assert "timed out" in plans[0]["error"]
    assert "secret" not in str(plans)


def test_deepseek_chat_url_normalizes_api_root() -> None:
    config = ModelConfig(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="secret",
    )

    assert config.chat_completions_url == "https://api.deepseek.com/v1/chat/completions"


def test_confirmation_request_uses_preview_token_and_agent_endpoint() -> None:
    preview = {
        "confirmation_required_for_write": True,
        "action": "inventory.adjust",
        "risk": "medium",
        "planned_request": {
            "endpoint": "POST /api/v1/inventory/ops/adjust/preview",
            "body": {"inventory_id": "inv-1", "new_quantity": 5, "reason": "Count"},
        },
        "confirmation_payload": {
            "confirmation_token": "inv-adjust:token",
            "evidence_id": "ev-1",
            "records": [{"id": "inv-1"}],
        },
    }

    card = extract_confirmation_card(preview)
    endpoint, body, key, headers = build_confirmation_request(preview, "idem-1")

    assert card is not None
    assert card["agent_endpoint"] == "/inventory/ops/adjust/agent"
    assert endpoint == "/inventory/ops/adjust/agent"
    assert body == {
        "inventory_id": "inv-1",
        "new_quantity": 5,
        "reason": "Count",
        "confirmation_token": "inv-adjust:token",
    }
    assert key == "idem-1"
    assert headers == {"X-Idempotency-Key": "idem-1"}


def test_confirmation_request_supports_settings_preview_card() -> None:
    preview = {
        "confirmation_required_for_write": True,
        "action": "settings.receiving_codes.update",
        "risk": "medium",
        "planned_request": {
            "endpoint": "POST /api/v1/agent/settings/receiving-codes/preview",
            "body": {"settings": {"prefix": "BOX", "sequence_padding": 3}},
        },
        "confirmation_payload": {
            "confirmation_token": "set-rcv-code:token",
            "evidence_id": "ev-settings-1",
        },
    }

    card = extract_confirmation_card(preview)
    endpoint, body, key, headers = build_confirmation_request(preview, "settings-idem-1")

    assert card["agent_endpoint"] == "/agent/settings/receiving-codes/agent"
    assert endpoint == "/agent/settings/receiving-codes/agent"
    assert body == {
        "settings": {"prefix": "BOX", "sequence_padding": 3},
        "confirmation_token": "set-rcv-code:token",
    }
    assert key == "settings-idem-1"
    assert headers == {"X-Idempotency-Key": "settings-idem-1"}


def test_confirmation_request_supports_second_batch_settings_card() -> None:
    preview = {
        "confirmation_required_for_write": True,
        "action": "settings.sku.update",
        "risk": "medium",
        "planned_request": {
            "endpoint": "POST /api/v1/agent/settings/sku/preview",
            "body": {"sku_id": "sku-1", "changes": {"name": "Updated SKU"}},
        },
        "confirmation_payload": {
            "confirmation_token": "set-sku:token",
            "evidence_id": "ev-settings-sku",
        },
    }

    card = extract_confirmation_card(preview)
    endpoint, body, key, headers = build_confirmation_request(preview, "settings-sku-idem")

    assert card["agent_endpoint"] == "/agent/settings/sku/agent"
    assert endpoint == "/agent/settings/sku/agent"
    assert body == {
        "sku_id": "sku-1",
        "changes": {"name": "Updated SKU"},
        "confirmation_token": "set-sku:token",
    }
    assert key == "settings-sku-idem"
    assert headers == {"X-Idempotency-Key": "settings-sku-idem"}


def test_confirmation_request_supports_import_preview_card() -> None:
    preview = {
        "confirmation_required_for_write": True,
        "action": "migration.inventory.import",
        "risk": "medium",
        "planned_request": {
            "endpoint": "POST /api/v1/agent/imports/inventory/preview",
            "body": {"csv_text": "sku_code,location_barcode,quantity\nSKU,A1,7\n"},
        },
        "confirmation_payload": {
            "confirmation_token": "imp-inventory:token",
            "evidence_id": "ev-import-1",
        },
    }

    card = extract_confirmation_card(preview)
    card = extract_confirmation_card(preview)
    assert requires_strong_confirmation(card) is True
    with pytest.raises(ConfirmationError, match="Strong confirmation"):
        build_confirmation_request(preview, "import-idem")

    endpoint, body, key, headers = build_confirmation_request(preview, "import-idem", "ev-import-1")

    assert card["agent_endpoint"] == "/agent/imports/inventory/agent"
    assert card["strong_confirmation_required"] is True
    assert card["strong_confirmation_phrase"] == "ev-import-1"
    assert endpoint == "/agent/imports/inventory/agent"
    assert body == {
        "csv_text": "sku_code,location_barcode,quantity\nSKU,A1,7\n",
        "confirmation_token": "imp-inventory:token",
    }
    assert key == "import-idem"
    assert headers == {"X-Idempotency-Key": "import-idem"}
