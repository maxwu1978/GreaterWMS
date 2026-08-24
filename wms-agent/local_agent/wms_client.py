"""Authenticated WMS API client used by the local agent."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import normalize_wms_api_url


class WmsApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    return str(payload)


class WmsClient:
    def __init__(self, api_base_url: str, token: str | None = None) -> None:
        self.api_base_url = normalize_wms_api_url(api_base_url)
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    async def login(self, email: str, password: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.api_base_url}/auth/login",
                    json={"email": email, "password": password},
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, "Timed out waiting for WMS login") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS login: {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def get_agent_settings(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.get(
                    f"{self.api_base_url}/agent/settings",
                    headers=self.headers,
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, "Timed out waiting for WMS agent settings") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS agent settings: {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def agent_settings(self, token: str) -> dict[str, Any]:
        return await WmsClient(self.api_base_url, token).get_agent_settings()

    async def get_evidence_detail(self, evidence_id: str) -> dict[str, Any]:
        safe_evidence_id = quote(evidence_id, safe="")
        path = f"/agent/evidence/{safe_evidence_id}"
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.get(
                    f"{self.api_base_url}{path}",
                    headers=self.headers,
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, "Timed out waiting for WMS evidence detail") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS evidence detail: {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def get_evidence_replay_preview(self, evidence_id: str) -> dict[str, Any]:
        safe_evidence_id = quote(evidence_id, safe="")
        path = f"/agent/evidence/{safe_evidence_id}/replay-preview"
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.get(
                    f"{self.api_base_url}{path}",
                    headers=self.headers,
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, "Timed out waiting for WMS evidence replay preview") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(
                502,
                f"Could not reach WMS evidence replay preview: {exc}",
            ) from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def get_failed_evidence(self) -> dict[str, Any]:
        path = "/agent/evidence/failed"
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.get(
                    f"{self.api_base_url}{path}",
                    headers=self.headers,
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, "Timed out waiting for WMS failed evidence") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS failed evidence: {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def run_tool(
        self,
        token_or_tool_name: str,
        tool_name_or_args: str | dict[str, Any] | None = None,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if isinstance(tool_name_or_args, str):
            token = token_or_tool_name
            tool_name = tool_name_or_args
            body_args = args or {}
        else:
            token = self.token
            tool_name = token_or_tool_name
            body_args = tool_name_or_args or {}
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.api_base_url}/agent/tools/run",
                    headers=headers,
                    json={"tool_name": tool_name, "args": body_args},
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, f"Timed out waiting for WMS tool '{tool_name}'") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS tool '{tool_name}': {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()

    async def post(
        self,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        merged_headers = {**self.headers, **(headers or {})}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.api_base_url}{path}",
                    headers=merged_headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise WmsApiError(504, f"Timed out waiting for WMS endpoint '{path}'") from exc
        except httpx.RequestError as exc:
            raise WmsApiError(502, f"Could not reach WMS endpoint '{path}': {exc}") from exc
        if response.status_code >= 400:
            raise WmsApiError(response.status_code, _detail(response))
        return response.json()
