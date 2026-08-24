from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.services.web_search_service import (
    deepseek_web_search_system_hint,
    deepseek_web_search_tools,
    execute_web_search_tool,
)


@dataclass(slots=True)
class ExternalAgentConfig:
    key: str
    label: str
    api_key: str
    base_url: str
    model: str
    provider_family: str = "openai_style"


class AgentTeamService:
    def __init__(self) -> None:
        self._configs = self._build_configs()

    def _build_configs(self) -> dict[str, ExternalAgentConfig]:
        configs: dict[str, ExternalAgentConfig] = {}
        if settings.MINIMAX_API_KEY:
            configs["minimax"] = ExternalAgentConfig(
                key="minimax",
                label="MiniMax",
                api_key=settings.MINIMAX_API_KEY,
                base_url=settings.MINIMAX_BASE_URL,
                model=settings.MINIMAX_MODEL,
            )
        if settings.QWEN_API_KEY:
            configs["qwen"] = ExternalAgentConfig(
                key="qwen",
                label="Qwen",
                api_key=settings.QWEN_API_KEY,
                base_url=settings.QWEN_BASE_URL,
                model=settings.QWEN_MODEL,
            )
        if settings.KIMI_API_KEY:
            configs["kimi"] = ExternalAgentConfig(
                key="kimi",
                label="Kimi",
                api_key=settings.KIMI_API_KEY,
                base_url=settings.KIMI_BASE_URL,
                model=settings.KIMI_MODEL,
            )
        if settings.DEEPSEEK_API_KEY:
            configs["deepseek"] = ExternalAgentConfig(
                key="deepseek",
                label="DeepSeek",
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                model=settings.DEEPSEEK_MODEL,
            )
        return configs

    def available_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "key": config.key,
                "label": config.label,
                "model": config.model,
                "base_url": config.base_url,
                "configured": True,
            }
            for config in self._configs.values()
        ]

    def _resolve_agents(self, requested_agents: list[str] | None) -> list[ExternalAgentConfig]:
        if not self._configs:
            raise HTTPException(
                status_code=400, detail="No external agent providers are configured"
            )
        if not requested_agents:
            return list(self._configs.values())
        resolved: list[ExternalAgentConfig] = []
        for key in requested_agents:
            config = self._configs.get(key)
            if not config:
                raise HTTPException(
                    status_code=400, detail=f"External agent '{key}' is not configured"
                )
            resolved.append(config)
        return resolved

    def _task_prompts(self, mode: str, task: str, context: str | None) -> tuple[str, str]:
        context_block = f"\n\nContext:\n{context.strip()}" if context and context.strip() else ""
        if mode == "summarize":
            system = (
                "You are part of a warehouse software agent team. "
                "Produce a concise operational summary with risks and recommended next step."
            )
            user = (
                f"Task:\n{task.strip()}{context_block}\n\n"
                "Return three sections:\n"
                "1. What matters most\n"
                "2. Risks or gaps\n"
                "3. Recommended next step"
            )
            return system, user
        if mode == "review":
            system = (
                "You are part of a warehouse software agent team. "
                "Review the proposal or code context for execution risk, regressions, and missing validation."
            )
            user = (
                f"Task:\n{task.strip()}{context_block}\n\n"
                "Return three sections:\n"
                "1. Findings\n"
                "2. Risks\n"
                "3. Recommendation"
            )
            return system, user
        system = (
            "You are part of a warehouse software agent team. "
            "Give a practical implementation viewpoint for the requested task."
        )
        user = (
            f"Task:\n{task.strip()}{context_block}\n\n"
            "Return three sections:\n"
            "1. Recommended approach\n"
            "2. Tradeoffs\n"
            "3. Execution notes"
        )
        return system, user

    async def _call_openai_style(
        self, config: ExternalAgentConfig, system_prompt: str, user_prompt: str
    ) -> str:
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        tools: list[dict[str, Any]] = []
        if config.key == "deepseek":
            tools = deepseek_web_search_tools()
            hint = deepseek_web_search_system_hint()
            if hint:
                system_prompt = f"{system_prompt}\n\n{hint}"
        body = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        for _ in range(4):
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail=f"External agent {config.label} error: {response.text[:300]}",
                )
            payload = response.json()
            try:
                choice = payload["choices"][0]
                message = choice["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"External agent {config.label} returned no message content",
                ) from exc

            tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
            if tools and tool_calls:
                body["messages"].append(message)
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    result = await execute_web_search_tool(
                        function.get("name"),
                        function.get("arguments"),
                    )
                    body["messages"].append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": result,
                        }
                    )
                continue

            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                return self._sanitize_content(content)

            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            detail = f"External agent {config.label} returned no message content"
            if finish_reason:
                detail = f"{detail} (finish_reason={finish_reason})"
            raise HTTPException(status_code=502, detail=detail)

        raise HTTPException(
            status_code=502,
            detail=f"External agent {config.label} exceeded web search tool loop limit",
        )

    @staticmethod
    def _sanitize_content(content: str) -> str:
        cleaned = content.strip()
        while "<think>" in cleaned and "</think>" in cleaned:
            start = cleaned.find("<think>")
            end = cleaned.find("</think>", start)
            if end == -1:
                break
            cleaned = (cleaned[:start] + cleaned[end + len("</think>") :]).strip()
        return cleaned

    async def _run_single(
        self, config: ExternalAgentConfig, mode: str, task: str, context: str | None
    ) -> dict[str, Any]:
        system_prompt, user_prompt = self._task_prompts(mode, task, context)
        answer = await self._call_openai_style(config, system_prompt, user_prompt)
        return {
            "agent": config.key,
            "label": config.label,
            "model": config.model,
            "answer": answer,
        }

    async def _synthesize(
        self, runs: list[dict[str, Any]], mode: str, task: str, context: str | None
    ) -> str:
        lead_key = "minimax" if any(run.get("agent") == "minimax" for run in runs) else runs[0]["agent"]
        lead = self._configs[lead_key]
        compiled = "\n\n".join(
            f"[{run['label']} / {run['model']}]\n{run['answer']}" for run in runs
        )
        system_prompt = (
            "You are the lead of a warehouse software agent team. "
            "Synthesize multiple model answers into one practical decision for execution."
        )
        context_block = f"\n\nContext:\n{context.strip()}" if context and context.strip() else ""
        user_prompt = (
            f"Original task:\n{task.strip()}{context_block}\n\n"
            f"Mode: {mode}\n\n"
            f"Team responses:\n{compiled}\n\n"
            "Return four sections:\n"
            "1. Recommended path\n"
            "2. Risks to watch\n"
            "3. What to do first\n"
            "4. What can wait"
        )
        return await self._call_openai_style(lead, system_prompt, user_prompt)

    async def run(
        self, mode: str, task: str, context: str | None = None, agents: list[str] | None = None
    ) -> dict[str, Any]:
        if mode not in {"compare", "summarize", "review"}:
            raise HTTPException(status_code=400, detail="Unsupported agent team mode")
        if not task.strip():
            raise HTTPException(status_code=400, detail="Agent team task is required")
        resolved_agents = self._resolve_agents(agents)
        runs = await asyncio.gather(
            *(self._run_single(config, mode, task, context) for config in resolved_agents)
        )
        synthesis = await self._synthesize(runs, mode, task, context)
        return {
            "mode": mode,
            "task": task,
            "agents": [run["agent"] for run in runs],
            "responses": runs,
            "synthesis": synthesis,
        }
