"""Optional web search tool support for model providers."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the public web for current or external information. "
            "Use this when the answer depends on recent facts, public web pages, "
            "prices, schedules, regulations, or other information not supplied in context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise search query.",
                },
                "topic": {
                    "type": "string",
                    "enum": ["general", "news", "finance"],
                    "description": "Search category. Use news for current events and finance for market data.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return, from 1 to the configured maximum.",
                },
            },
            "required": ["query"],
        },
    },
}


def deepseek_web_search_enabled() -> bool:
    provider = settings.WEB_SEARCH_PROVIDER.strip().lower()
    return bool(
        settings.DEEPSEEK_WEB_SEARCH_ENABLED
        and provider == "tavily"
        and settings.TAVILY_API_KEY.strip()
    )


def deepseek_web_search_tools() -> list[dict[str, Any]]:
    return [WEB_SEARCH_TOOL] if deepseek_web_search_enabled() else []


def deepseek_web_search_system_hint() -> str:
    if not deepseek_web_search_enabled():
        return ""
    return (
        "Web search is available through the web_search tool. Use it when the user asks for "
        "latest/current information or facts outside the supplied context. Base the final "
        "answer on the returned snippets and include source URLs when relevant."
    )


async def execute_web_search_tool(name: str, raw_arguments: Any) -> str:
    if name != "web_search":
        return json.dumps({"error": "unknown_tool", "tool": name}, ensure_ascii=False)

    arguments = _parse_arguments(raw_arguments)
    query = str(arguments.get("query") or "").strip()
    if not query:
        return json.dumps({"error": "missing_query"}, ensure_ascii=False)

    topic = str(arguments.get("topic") or "general").strip().lower()
    if topic not in {"general", "news", "finance"}:
        topic = "general"

    max_results = _coerce_max_results(arguments.get("max_results"))

    provider = settings.WEB_SEARCH_PROVIDER.strip().lower()
    if provider != "tavily":
        return json.dumps(
            {"error": "unsupported_web_search_provider", "provider": provider},
            ensure_ascii=False,
        )
    if not settings.TAVILY_API_KEY.strip():
        return json.dumps(
            {"error": "web_search_not_configured", "missing": "TAVILY_API_KEY"},
            ensure_ascii=False,
        )

    return await _search_tavily(query=query, topic=topic, max_results=max_results)


def _parse_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str) and raw_arguments.strip():
        try:
            value = json.loads(raw_arguments)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}
    return {}


def _coerce_max_results(value: Any) -> int:
    configured_max = max(1, min(int(settings.WEB_SEARCH_MAX_RESULTS or 5), 10))
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = configured_max
    return max(1, min(requested, configured_max))


async def _search_tavily(*, query: str, topic: str, max_results: int) -> str:
    url = f"{settings.TAVILY_BASE_URL.rstrip('/')}/search"
    request_body: dict[str, Any] = {
        "query": query,
        "topic": topic,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.TAVILY_API_KEY.strip()}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, headers=headers, json=request_body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return json.dumps(
            {"error": "web_search_failed", "message": str(exc), "query": query},
            ensure_ascii=False,
        )

    payload = response.json()
    results = []
    for item in list(payload.get("results") or [])[:max_results]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "published_date": item.get("published_date"),
                "score": item.get("score"),
            }
        )

    return json.dumps(
        {
            "query": payload.get("query") or query,
            "answer": payload.get("answer"),
            "results": results,
        },
        ensure_ascii=False,
    )
