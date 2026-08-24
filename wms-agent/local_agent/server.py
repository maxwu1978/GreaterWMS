"""Local WMS Agent server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from .audit import AuditLog
from .config import LocalAgentSettings, normalize_wms_api_url
from .confirmation import (
    ConfirmationError,
    build_confirmation_request,
    extract_confirmation_card,
)
from .model_adapter import ModelAdapter, ModelConfig, compare_model_plans
from .policy import allowed_tool_keys, require_tool
from .router import looks_like_write, route_prompt
from .session import SessionStore
from .skills import SkillRegistry
from .wms_client import WmsApiError, WmsClient

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="WMS Local Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

sessions = SessionStore()
runtime_settings = LocalAgentSettings()
skills = SkillRegistry(runtime_settings.skill_root)
audit = AuditLog(runtime_settings.audit_log_path)


class LoginRequest(BaseModel):
    wms_api_base_url: str
    email: EmailStr
    password: str


class ToolRunRequest(BaseModel):
    session_id: str
    tool_name: str
    args: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    session_id: str
    prompt: str


class PlanCompareRequest(BaseModel):
    session_id: str
    prompt: str


class ConfirmRequest(BaseModel):
    session_id: str
    preview_payload: dict[str, Any]
    idempotency_key: str | None = None
    strong_confirmation: str | None = None


def _allowed_tool_keys(session) -> set[str]:
    return allowed_tool_keys(session.agent_settings or {})


def _guard_tool(session, tool_name: str, source: str):
    decision = require_tool(session.agent_settings or {}, tool_name)
    if not decision.allowed:
        audit.append(
            "tool_blocked",
            {
                "session_id": session.id,
                "tenant_id": session.tenant_id,
                "tool_name": tool_name,
                "source": source,
                "reason": decision.reason,
            },
        )
        raise HTTPException(status_code=403, detail=decision.reason or "Tool is not allowed")
    return decision


def _safe_model_tool_choice(
    session,
    model_plan: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    tool_name = model_plan.get("suggested_tool")
    raw_args = model_plan.get("suggested_args")
    args = raw_args if isinstance(raw_args, dict) else {}
    if not isinstance(tool_name, str) or not tool_name:
        return None, {}
    if tool_name not in _allowed_tool_keys(session):
        return None, {}
    return tool_name, args


def _model_configs() -> list[ModelConfig]:
    return [
        ModelConfig(
            provider=item["provider"],
            base_url=item["base_url"],
            model=item["model"],
            api_key=item["api_key"],
        )
        for item in runtime_settings.backend_model_configs
    ]


def _model_adapter() -> ModelAdapter:
    return ModelAdapter(
        ModelConfig(
            provider=runtime_settings.effective_model_provider,
            base_url=runtime_settings.effective_model_base_url,
            model=runtime_settings.effective_model_name,
            api_key=runtime_settings.effective_model_api_key,
        )
    )


def _public_skill_matches(prompt: str, limit: int = 3) -> list[dict[str, object]]:
    return [match.to_public_dict() for match in skills.explain_selection(prompt, limit=limit)]


def _skills_from_matches(matches: list[dict[str, object]]) -> list:
    by_name = {skill.name: skill for skill in skills.discover()}
    selected = []
    for match in matches:
        skill = by_name.get(str(match.get("name") or ""))
        if skill:
            selected.append(skill)
    return selected


def _adjudicate_model_plans(
    session,
    plans: list[dict[str, Any]],
    prompt: str,
) -> dict[str, Any]:
    rejected: list[dict[str, Any]] = []
    for plan in plans:
        tool_name = plan.get("suggested_tool")
        if not isinstance(tool_name, str) or not tool_name:
            rejected.append(
                {
                    "provider": plan.get("provider"),
                    "tool_name": tool_name,
                    "reason": "no tool suggested",
                }
            )
            continue
        decision = require_tool(session.agent_settings or {}, tool_name)
        if not decision.allowed:
            rejected.append(
                {
                    "provider": plan.get("provider"),
                    "tool_name": tool_name,
                    "reason": decision.reason,
                }
            )
            continue
        raw_args = plan.get("suggested_args")
        return {
            "selected_provider": plan.get("provider"),
            "selected_tool": tool_name,
            "selected_args": raw_args if isinstance(raw_args, dict) else {},
            "confidence": plan.get("confidence"),
            "rejected": rejected,
        }
    routed_tool, routed_args = route_prompt(prompt)
    return {
        "selected_provider": None,
        "selected_tool": routed_tool,
        "selected_args": routed_args,
        "confidence": None,
        "rejected": rejected,
    }


def _session_or_401(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Local WMS session is missing or expired")
    return session


def _active_session_or_401(session_id: str | None = None):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Local WMS session is missing or expired")
    return session


def _public_session(session) -> dict[str, Any]:
    settings = session.agent_settings or {}
    return {
        "session_id": session.id,
        "wms_api_base_url": session.wms_api_base_url,
        "tenant_id": session.tenant_id,
        "role": session.role,
        "job_title": session.job_title,
        "permissions": session.permissions,
        "agent_enabled": settings.get("enabled", False),
        "allowed_tools": settings.get("allowed_tools", []),
        "tool_catalog": settings.get("tool_catalog", []),
        "provider_label": settings.get("provider_label"),
        "model_name": settings.get("model_name"),
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "wms-local-agent"}


@app.get("/api/skills")
async def list_skills():
    return {
        "skills": [
            {"name": skill.name, "description": skill.description, "path": skill.path}
            for skill in skills.discover()
        ]
    }


@app.post("/api/plans/compare")
async def compare_planners(body: PlanCompareRequest):
    session = _session_or_401(body.session_id)
    selected_skill_matches = _public_skill_matches(body.prompt, limit=3)
    selected_skills = _skills_from_matches(selected_skill_matches)
    plans = await compare_model_plans(
        configs=_model_configs(),
        session=session,
        prompt=body.prompt,
        selected_skills=selected_skills,
    )
    adjudication = _adjudicate_model_plans(session, plans, body.prompt)
    audit.append(
        "planner_comparison",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "prompt": body.prompt,
            "selected_skills": selected_skill_matches,
            "providers": [plan.get("provider") for plan in plans],
            "adjudication": adjudication,
        },
    )
    return {
        "ok": True,
        "message": "Compared configured local model planners without executing WMS tools.",
        "selected_skills": selected_skill_matches,
        "plans": plans,
        "adjudication": adjudication,
    }


@app.get("/api/config")
async def local_config():
    return {
        "host": runtime_settings.host,
        "port": runtime_settings.port,
        "default_wms_api_base_url": runtime_settings.api_v1_url,
        "model_provider": runtime_settings.effective_model_provider,
        "model_name": runtime_settings.effective_model_name,
        "model_configured": bool(
            runtime_settings.effective_model_api_key and runtime_settings.effective_model_name
        ),
        "model_source": runtime_settings.effective_model_source,
        "model_roster": runtime_settings.backend_model_roster,
        "skill_root": str(runtime_settings.skill_root),
        "audit_log_path": str(runtime_settings.audit_log_path),
    }


@app.get("/api/audit")
async def audit_tail(limit: int = 50):
    return {"events": audit.tail(limit)}


@app.post("/api/session/login")
async def login(body: LoginRequest):
    api_base_url = normalize_wms_api_url(body.wms_api_base_url)
    client = WmsClient(api_base_url)
    try:
        token = await client.login(str(body.email), body.password)
        settings = await WmsClient(api_base_url, token["access_token"]).get_agent_settings()
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    session = sessions.create(
        wms_api_base_url=api_base_url,
        access_token=token["access_token"],
        role=token.get("role") or "",
        tenant_id=token.get("tenant_id"),
        job_title=token.get("job_title"),
        permissions=token.get("permissions") or [],
        agent_settings=settings,
    )
    audit.append(
        "login",
        {
            "wms_api_base_url": api_base_url,
            "email": str(body.email),
            "tenant_id": session.tenant_id,
            "role": session.role,
            "allowed_tool_count": len(settings.get("allowed_tools") or []),
        },
    )
    return _public_session(session)


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    return _public_session(_session_or_401(session_id))


@app.delete("/api/session/{session_id}")
async def logout(session_id: str):
    sessions.delete(session_id)
    audit.append("logout", {"session_id": session_id})
    return {"ok": True}


@app.get("/api/evidence/failed")
async def get_failed_evidence(
    session_id: str | None = Query(default=None),
):
    session = _active_session_or_401(session_id)
    try:
        failed = await WmsClient(
            session.wms_api_base_url,
            session.access_token,
        ).get_failed_evidence()
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    audit.append(
        "evidence_failed",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
        },
    )
    return {"ok": True, "failed_evidence": failed}


@app.get("/api/evidence/{evidence_id}/replay-preview")
async def get_evidence_replay_preview(
    evidence_id: str,
    session_id: str | None = Query(default=None),
):
    session = _active_session_or_401(session_id)
    try:
        preview = await WmsClient(
            session.wms_api_base_url,
            session.access_token,
        ).get_evidence_replay_preview(evidence_id)
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    audit.append(
        "evidence_replay_preview",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "evidence_id": evidence_id,
        },
    )
    return {"ok": True, "replay_preview": preview}


@app.get("/api/evidence/{evidence_id}")
async def get_evidence_detail(
    evidence_id: str,
    session_id: str | None = Query(default=None),
):
    session = _active_session_or_401(session_id)
    try:
        evidence = await WmsClient(
            session.wms_api_base_url,
            session.access_token,
        ).get_evidence_detail(evidence_id)
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    audit.append(
        "evidence_detail",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "evidence_id": evidence_id,
        },
    )
    return {"ok": True, "evidence": evidence}


@app.post("/api/tools/run")
async def run_tool(body: ToolRunRequest):
    session = _session_or_401(body.session_id)
    _guard_tool(session, body.tool_name, "explicit")
    try:
        result = await WmsClient(session.wms_api_base_url, session.access_token).run_tool(
            body.tool_name,
            body.args,
        )
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    audit.append(
        "tool_run",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "tool_name": body.tool_name,
            "args": body.args or {},
            "risk": result.get("risk"),
        },
    )
    confirmation_card = extract_confirmation_card(result) if isinstance(result, dict) else None
    return {
        "ok": result.get("ok", True) if isinstance(result, dict) else True,
        "tool_result": result,
        "confirmation_card": confirmation_card,
    }


@app.post("/api/confirm")
async def confirm_preview(body: ConfirmRequest):
    session = _session_or_401(body.session_id)
    try:
        endpoint, request_body, idempotency_key, headers = build_confirmation_request(
            body.preview_payload,
            body.idempotency_key,
            body.strong_confirmation,
        )
        result = await WmsClient(session.wms_api_base_url, session.access_token).post(
            endpoint,
            request_body,
            headers=headers,
        )
    except ConfirmationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    audit.append(
        "confirmation_executed",
        {
            "session_id": session.id,
            "tenant_id": session.tenant_id,
            "endpoint": endpoint,
            "idempotency_key": idempotency_key,
            "evidence_id": extract_confirmation_card(body.preview_payload).get("evidence_id")
            if extract_confirmation_card(body.preview_payload)
            else None,
        },
    )
    return {
        "ok": True,
        "confirmed": True,
        "endpoint": endpoint,
        "idempotency_key": idempotency_key,
        "result": result,
    }


@app.post("/api/chat")
async def chat(body: ChatRequest):
    session = _session_or_401(body.session_id)
    selected_skill_matches = _public_skill_matches(body.prompt, limit=3)
    selected_skills = _skills_from_matches(selected_skill_matches)
    if looks_like_write(body.prompt):
        model_plan = {
            "enabled": False,
            "skipped": True,
            "reason": "write-like prompt blocked before model planning",
        }
        audit.append(
            "chat_blocked_write",
            {
                "session_id": session.id,
                "prompt": body.prompt,
                "selected_skills": selected_skill_matches,
                "model_plan": model_plan,
            },
        )
        return {
            "ok": True,
            "blocked": True,
            "confirmation_required": True,
            "message": (
                "This looks like a write request. The local agent will stop here until "
                "a WMS preview returns an explicit confirmation token."
            ),
            "selected_skills": selected_skill_matches,
            "model_plan": model_plan,
            "tool_result": None,
        }
    model_plan = await _model_adapter().plan(
        session=session,
        prompt=body.prompt,
        selected_skills=selected_skills,
    )
    tool_name, args = _safe_model_tool_choice(session, model_plan)
    if not tool_name:
        tool_name, args = route_prompt(body.prompt)
    if not tool_name:
        audit.append(
            "chat_unrouted",
            {
                "session_id": session.id,
                "prompt": body.prompt,
                "selected_skills": selected_skill_matches,
                "model_plan": model_plan,
            },
        )
        return {
            "ok": False,
            "message": (
                "I need a more specific WMS request, such as inventory, clients, "
                "inbound, outbound, billing, warehouse, or setup."
            ),
            "selected_skills": selected_skill_matches,
            "model_plan": model_plan,
            "tool_result": None,
        }
    _guard_tool(session, tool_name, "chat")

    try:
        tool_result = await WmsClient(session.wms_api_base_url, session.access_token).run_tool(
            tool_name,
            args,
        )
    except WmsApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    audit.append(
        "chat_tool_run",
        {
            "session_id": session.id,
            "prompt": body.prompt,
            "selected_skills": selected_skill_matches,
            "tool_name": tool_name,
            "args": args,
            "model_plan": model_plan,
        },
    )
    confirmation_card = extract_confirmation_card(tool_result)
    return {
        "ok": True,
        "message": f"Ran {tool_name} through the authenticated WMS agent tool gate.",
        "selected_skills": selected_skill_matches,
        "model_plan": model_plan,
        "tool_result": tool_result,
        "confirmation_card": confirmation_card,
    }


def main() -> None:
    settings = LocalAgentSettings()
    uvicorn.run(
        "local_agent.server:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
