"""Model-backed explanations for the tenant agent console."""

from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import HTTPException

from app.services.web_search_service import (
    deepseek_web_search_system_hint,
    deepseek_web_search_tools,
    execute_web_search_tool,
)


class AgentModelService:
    def __init__(self, settings_payload: dict[str, Any]):
        self.settings_payload = settings_payload
        self.provider_type = str(settings_payload.get("provider_type") or "").strip()
        self.provider_label = str(settings_payload.get("provider_label") or "").strip() or None
        self.base_url = str(settings_payload.get("base_url") or "").strip()
        self.model_name = str(settings_payload.get("model_name") or "").strip()
        self.region = str(settings_payload.get("region") or "").strip() or None
        self.api_key = str(settings_payload.get("api_key") or "").strip()

    def _ensure_ready(self) -> None:
        if not self.provider_type:
            raise HTTPException(status_code=400, detail="Agent provider is not configured")
        if not self.model_name:
            raise HTTPException(status_code=400, detail="Agent model name is not configured")
        if not self.api_key:
            raise HTTPException(status_code=400, detail="Agent provider secret is not configured")

    async def validate_configuration(self) -> dict[str, Any]:
        self._ensure_ready()
        provider = self.provider_type
        if provider in {"aws_bedrock", "google_vertex_ai"}:
            return {
                "status": "unsupported",
                "message": f"Provider '{provider}' is not wired for runtime validation yet",
            }

        system_prompt = "Reply with exactly OK."
        user_prompt = "Health check"
        answer = await self._generate_text(system_prompt, user_prompt)
        return {
            "status": "valid",
            "message": f"Validated {self.provider_type} / {self.model_name}",
            "answer": answer.strip(),
        }

    async def explain_inventory(
        self, query: str, inventory_payload: dict[str, Any], language: str | None = None
    ) -> dict[str, Any]:
        self._ensure_ready()
        items = list(inventory_payload.get("items") or [])[:12]
        language_instruction = self._language_instruction(language)
        system_prompt = (
            "You are a warehouse operations copilot. Explain inventory in plain business language. "
            "Be concise, avoid jargon, and focus on stock levels, allocation pressure, and what the operator should notice next. "
            f"{language_instruction}"
        )
        user_prompt = (
            f"User query: {query or 'inventory overview'}\n"
            f"Returned rows: {inventory_payload.get('count', len(items))}\n"
            "Inventory snapshot:\n"
            f"{items}\n\n"
            "Reply with 3 short sections:\n"
            "1. What the inventory picture says\n"
            "2. Any pressure or risk worth noticing\n"
            "3. Suggested next step"
        )
        answer = await self._generate_text(system_prompt, user_prompt)
        answer = self._strip_thinking(answer)
        answer = await self._ensure_answer_language(answer, language)
        return {
            "query": query or None,
            "provider_type": self.provider_type,
            "provider_label": self.provider_label or self.provider_type,
            "model_name": self.model_name,
            "items_considered": len(items),
            "source_count": inventory_payload.get("count", len(items)),
            "answer": answer,
            "inventory_snapshot": items,
        }

    def _language_instruction(self, language: str | None) -> str:
        normalized = (language or "").strip().lower()
        if normalized in {"zh-hant", "zh_hant", "zh-tw", "zh_tw"}:
            return (
                "Reply entirely in Traditional Chinese used in Taiwan. "
                "Do not switch to English headings, bullet labels, or summary sentences. "
                "Return only the final answer body."
            )
        if normalized in {"es", "es-es", "es_mx"}:
            return "Reply entirely in Spanish. Return only the final answer body."
        if normalized in {"hu", "hu-hu"}:
            return "Reply entirely in Hungarian. Return only the final answer body."
        if normalized in {"de", "de-de"}:
            return "Reply entirely in German. Return only the final answer body."
        return "Reply entirely in English. Return only the final answer body."

    def _strip_thinking(self, answer: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", answer, flags=re.IGNORECASE | re.DOTALL).strip()
        return cleaned or answer.strip()

    def _needs_language_retry(self, answer: str, language: str | None) -> bool:
        normalized = (language or "").strip().lower()
        if not normalized:
            return False

        sample = answer.strip()
        if not sample:
            return False

        if normalized in {"zh-hant", "zh_hant", "zh-tw", "zh_tw"}:
            has_cjk = bool(re.search(r"[\u4e00-\u9fff]", sample))
            english_markers = len(re.findall(r"[A-Za-z]{4,}", sample))
            return not has_cjk or english_markers >= 8
        if normalized in {"es", "es-es", "es_mx"}:
            return "the inventory" in sample.lower() or "suggested next step" in sample.lower()
        if normalized in {"hu", "hu-hu"}:
            return "the inventory" in sample.lower() or "suggested next step" in sample.lower()
        if normalized in {"de", "de-de"}:
            return "the inventory" in sample.lower() or "suggested next step" in sample.lower()
        return False

    async def _ensure_answer_language(self, answer: str, language: str | None) -> str:
        if not self._needs_language_retry(answer, language):
            return answer

        language_instruction = self._language_instruction(language)
        translated = await self._generate_text(
            (
                "You are rewriting an existing warehouse answer into the requested UI language. "
                f"{language_instruction}"
            ),
            (
                "Rewrite the following answer into the requested language. "
                "Keep the meaning, structure, and section order. "
                "Do not add commentary.\n\n"
                f"{answer}"
            ),
        )
        return self._strip_thinking(translated)

    async def _generate_text(self, system_prompt: str, user_prompt: str) -> str:
        provider = self.provider_type
        if provider in {
            "openai",
            "openai_compatible",
            "kimi",
            "minimax",
            "deepseek",
            "azure_openai",
        }:
            return await self._call_openai_style(system_prompt, user_prompt)
        if provider == "anthropic_claude":
            return await self._call_anthropic(system_prompt, user_prompt)
        if provider == "google_gemini":
            return await self._call_gemini(system_prompt, user_prompt)
        if provider in {"aws_bedrock", "google_vertex_ai"}:
            raise HTTPException(
                status_code=501,
                detail=f"Provider '{provider}' is not wired for runtime execution yet",
            )
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'")

    async def _call_openai_style(self, system_prompt: str, user_prompt: str) -> str:
        base_url = self.base_url or "https://api.openai.com/v1"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        url = ""
        tools: list[dict[str, Any]] = []

        if self.provider_type == "azure_openai" and "openai.azure.com" in base_url:
            url = (
                f"{base_url.rstrip('/')}/openai/deployments/{self.model_name}/chat/completions"
                "?api-version=2024-10-21"
            )
            headers["api-key"] = self.api_key
            body = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
        else:
            url = f"{base_url.rstrip('/')}/chat/completions"
            headers["Authorization"] = f"Bearer {self.api_key}"
            if self.provider_type == "deepseek":
                tools = deepseek_web_search_tools()
                hint = deepseek_web_search_system_hint()
                if hint:
                    system_prompt = f"{system_prompt}\n\n{hint}"
            body = {
                "model": self.model_name,
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
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=502, detail=f"Model provider error: {response.text[:300]}"
                )
            payload = response.json()
            try:
                choice = payload["choices"][0]
                message = choice["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise HTTPException(
                    status_code=502, detail="Model provider response was missing message content"
                ) from exc

            tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
            if tools and tool_calls:
                body["messages"].append(message)
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function") or {}
                    tool_name = function.get("name")
                    tool_arguments = function.get("arguments")
                    result = await execute_web_search_tool(tool_name, tool_arguments)
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
                return content.strip()

            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            detail = "Model provider response was missing message content"
            if finish_reason:
                detail = f"{detail} (finish_reason={finish_reason})"
            raise HTTPException(status_code=502, detail=detail)

        raise HTTPException(status_code=502, detail="Model provider exceeded web search tool loop limit")

    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        base_url = self.base_url or "https://api.anthropic.com"
        url = f"{base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model_name,
            "system": system_prompt,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"Model provider error: {response.text[:300]}"
            )
        payload = response.json()
        try:
            parts = payload["content"]
            text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
            answer = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
            if answer:
                return answer
        except (KeyError, TypeError):
            pass
        raise HTTPException(status_code=502, detail="Model provider response was missing content")

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        base_url = self.base_url or "https://generativelanguage.googleapis.com"
        url = f"{base_url.rstrip('/')}/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=body)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"Model provider error: {response.text[:300]}"
            )
        payload = response.json()
        try:
            candidate = payload["candidates"][0]
            parts = candidate["content"]["parts"]
            answer = "\n".join(
                part.get("text", "").strip() for part in parts if isinstance(part, dict)
            ).strip()
            if answer:
                return answer
        except (KeyError, IndexError, TypeError):
            pass
        raise HTTPException(status_code=502, detail="Model provider response was missing content")
